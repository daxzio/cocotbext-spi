# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2021 Spencer Chang
from cocotb.triggers import First
from cocotb.triggers import RisingEdge

from cocotbext.spi.exceptions import SpiFrameError
from cocotbext.spi.spi import reverse_word
from cocotbext.spi.spi import SpiBus
from cocotbext.spi.spi import SpiConfig
from cocotbext.spi.spi import SpiSlaveBase
from enum import Enum

from typing import Optional
from cocotb.triggers import Edge

class Commands(Enum):
    READ = 0x03
    FAST_READ = 0x0b
    DOR = 0x3b
    QOR = 0x6b
    DIOR = 0xbb
    QIOR = 0xeb
    RDID = 0x9f
    READ_ID = 0x90
    WREN = 0x06
    WRDI = 0x04
    P4E = 0x20
    P8E = 0x40
    SE = 0xd8
    BE = 0x60
    BE2 = 0xc7
    PP = 0x02
    QPP = 0x32
    RDSR = 0x05
    WRR = 0x01
    RCR = 0x35
    CLSR = 0x30
    DP = 0xb9
    RES = 0xab
    OTPP = 0x42
    OTPR = 0x4b


class Memory:
    def __init__(self, data=None):
        self._data = data or {}
        self.depth = 4096

    def __getitem__(self, index):
        try:
            self._data[index]
        except KeyError:
            self._data[index] = 0xFF
        return self._data[index]

    def __setitem__(self, index, value):
        try:
            self._data[index] = self._data[index] & value
        except KeyError:
            self._data[index] = value

    def __len__(self):
        return self.depth

    def erase(self):
        for i in range(self.depth):
            self._data.pop(i, None)



class S25FL(SpiSlaveBase):
    
    _config = SpiConfig(
        word_width=5 * 8,
        cpol=False,
        cpha=False,
        msb_first=True,
        frame_spacing_ns=400,
        cs_active_low=True,
    )

    def __init__(self, bus: SpiBus):
        self._mem = Memory()

        self.id = [0x7e, 0x02, 0x19]
        self.status = 0x38
        self.config_reg = 0x63

        self.write = False

        super().__init__(bus)

    async def _shift(self, num_bits: int, tx_word: Optional[int] = None) -> int:
        """ Shift in data on the MOSI signal. Shift out the tx_word on the MISO signal.

        Args:
            num_bits: the number of bits to shift
            tx_word: the word to be transmitted on the wire

        Returns:
            the received word on the MOSI line
        """
        rx_word = 0

        frame_end = RisingEdge(self._cs) if self._config.cs_active_low else FallingEdge(self._cs)

        for k in range(num_bits):
            if not self._config.cpha:
                if tx_word is not None:
                    self._miso.value = bool(tx_word & (1 << (num_bits - 1 - k)))
                else:
                    self._miso.value = self._config.data_output_idle
            
            # If both events happen at the same time, the returned one is indeterminate, thus
            # checking for cs = 1
            if (await First(Edge(self._sclk), frame_end)) == frame_end or self._cs.value == 1:
                raise SpiFrameError("End of frame in the middle of a transaction")

            if self._config.cpha:
                # when CPHA=1, the slave should shift out on the first edge
                if tx_word is not None:
                    self._miso.value = bool(tx_word & (1 << (num_bits - 1 - k)))
                else:
                    self._miso.value = self._config.data_output_idle
            else:
                # when CPHA=0, the slave should sample on the first edge
                rx_word |= int(self._mosi.value.integer) << (num_bits - 1 - k)
                if k == num_bits-1:
                    break

            # do the opposite of what was done on the first edge
            if (await First(Edge(self._sclk), frame_end)) == frame_end or self._cs.value == 1:
                raise SpiFrameError("End of frame in the middle of a transaction")

            if self._config.cpha:
                rx_word |= int(self._mosi.value.integer) << (num_bits - 1 - k)

        return rx_word

    async def _transaction(self, frame_start, frame_end):
        await frame_start
        self.idle.clear()

        # SCLK pin should be low at the chip select edge
        if bool(self._sclk.value):
            raise SpiFrameError("S25FL: sclk should be low at chip select edge")

        command = int(await self._shift(8))
        self.log.info(f"command 0x{command:02x} -> {Commands(command).name}")
        self.index = 0
        txn = False
        if Commands.READ.value == command:
            address = int(await self._shift(24))
            self.index = address
            array = self._mem
            txn = True
        elif Commands.FAST_READ.value == command:
            address = int(await self._shift(24))
            dummy = int(await self._shift(8))
            self.index = address
            array = self._mem
            txn = True
        elif Commands.RDID.value == command:
            array = self.id
            txn = True
        elif Commands.RDSR.value == command:
            array = [self.status]
            txn = True
        elif Commands.RCR.value == command:
            array = [self.config_reg]
            txn = True
        elif Commands.WRR.value == command:
            self.status = int(await self._shift(8))
            try:
                self.config_reg = int(await self._shift(8))
            except SpiFrameError:
                pass
        elif Commands.WREN.value == command:
            self.write = True
            self.log.info(f"Enable Write")
        elif Commands.WRDI.value == command:
            pass
        elif Commands.PP.value == command:
            address = int(await self._shift(24))
            self.index = address
            array = self._mem
            txn = True
        elif Commands.BE.value == command or Commands.BE2.value == command :
            if self.write:
                self.log.info(f"Erasing Flash")
                self._mem.erase()
        else:
            raise Exception(f"Unimplemented command {Commands(command).name}")

        if txn:
            while True:
                if self.write:
                    tx_word = 0xFF
                else:
                    tx_word = array[self.index]
                try:
                    x = await self._shift(8, tx_word=tx_word)
                    content = int(x)
                    if self.write:
                        array[self.index] = content
                    self.index = (self.index + 1) % len(array)
                except SpiFrameError:
                    break

        if (
            Commands.WRDI.value == command
            or Commands.WRR.value == command
            or Commands.PP.value == command
            or Commands.QPP.value == command
            or Commands.P4E.value == command
            or Commands.P8E.value == command
            or Commands.SE.value == command
            or Commands.BE.value == command
            or Commands.BE2.value == command
            or Commands.OTPP.value == command
        ):
            if self.write:
                self.log.info(f"Disable Write")
            self.write = False

        #         # end of frame
        #         if await First(frame_end, RisingEdge(self._sclk)) != frame_end:
        #             raise SpiFrameError("S25FL: clocked more than 40 bits")

        if bool(self._sclk.value):
            raise SpiFrameError("S25FL: sclk should be low at chip select edge")
