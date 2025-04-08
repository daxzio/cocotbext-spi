# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2021 Spencer Chang
import logging
from cocotb import start_soon
from cocotb.triggers import First
from cocotb.triggers import RisingEdge
from cocotb.triggers import FallingEdge
from cocotb.triggers import Timer
from cocotb.utils import get_sim_time

from cocotbext.spi.exceptions import SpiFrameError

# from cocotbext.spi.spi import reverse_word
from cocotbext.spi.spi import SpiBus
from cocotbext.spi.spi import SpiConfig
from cocotbext.spi.spi import SpiSlaveBase
from enum import Enum

from typing import Optional
from cocotb.triggers import Edge


class Commands(Enum):
    READ = 0x03
    FAST_READ = 0x0B
    DOR = 0x3B
    QOR = 0x6B
    DIOR = 0xBB
    QIOR = 0xEB
    RDID = 0x9F
    READ_ID = 0x90
    WREN = 0x06
    WRDI = 0x04
    P4E = 0x20
    P8E = 0x40
    SE = 0xD8
    BE = 0x60
    BE2 = 0xC7
    PP = 0x02
    QPP = 0x32
    RDSR = 0x05
    WRR = 0x01
    RCR = 0x35
    CLSR = 0x30
    DP = 0xB9
    RES = 0xAB
    OTPP = 0x42
    OTPR = 0x4B


class Memory:
    def __init__(self, depth: int = 16777216, data=None):
        self._data = data or {}
        self.depth = depth
        # self.depth = 16777216 # 16 MB
        # self.depth = 1048576 # 64 kB
        self.log = logging.getLogger(f"cocotb.Memory")

    def test_index(self, index):
        new_index = index % self.depth
        if index >= self.depth:
            self.log.warning(
                f"Address 0x{index:08x} is larger than memory 0x{self.depth:08x}, wrapping 0x{new_index:08x}"
            )
        return new_index

    def __getitem__(self, index):
        index = self.test_index(index)
        try:
            self._data[index]
        except KeyError:
            self._data[index] = 0xFF
        return self._data[index]

    def __setitem__(self, index, value):
        index = self.test_index(index)
        try:
            self._data[index] = self._data[index] & value
        except KeyError:
            self._data[index] = value

    def __len__(self):
        return self.depth

    def erase(self, address: int = 0, length: int = -1):
        if length < 0:
            length = self.depth
        start = address & (0xffffffff ^ (length-1))
        end = start + length
        if not start == address:
            self.log.warning(
                f"Address 0x{address:08x} is not sector aligned using this sector start 0x{start:08x} -> 0x{end:08x}"
            )
        keys = set(self._data.keys())
        for i in keys:
            if i >= start and i < end:
                self._data.pop(i, None)

class S25FL(SpiSlaveBase):

    _config = SpiConfig(
        cpol=False,
        cpha=False,
        msb_first=True,
        frame_spacing_ns=400,
        cs_active_low=True,
    )

    def __init__(self, bus: SpiBus, mem_size: int = 16777216, mode: int = 0):
        self.mode = mode
        if 0 == self.mode:
            self._config.cpol = False
            self._config.cpha = False
        elif 1 == self.mode:
            self._config.cpol = True
            self._config.cpha = True
        else:
            raise Exception(f"Unknown operation mode: {self.mode}")
        self._mem = Memory(mem_size)

        self.id = [
            0x01,
            0x02,
            0x19,
            0x4D,
            0x01,
            0x80,
            0x30,
            0x30,
            0x81,
            0xFF,
            0xFF,
            0xFF,
            0xFF,
            0xFF,
            0xFF,
            0xFF,
            0x51,
            0x52,
            0x59,
            0x02,
            0x00,
            0x40,
            0x00,
            0x53,
            0x46,
            0x51,
            0x00,
            0x27,
            0x36,
            0x00,
            0x00,
            0x06,
            0x08,
            0x08,
            0x10,
            0x02,
            0x02,
            0x03,
            0x03,
            0x19,
            0x02,
            0x01,
            0x08,
            0x00,
            0x02,
            0x1F,
            0x00,
            0x10,
            0x00,
            0xFD,
            0x01,
            0x00,
            0x01,
            0xFF,
            0xFF,
            0xFF,
            0xFF,
            0xFF,
            0xFF,
            0xFF,
            0xFF,
            0xFF,
            0xFF,
            0xFF,
            0x50,
            0x52,
            0x49,
            0x31,
            0x33,
            0x21,
            0x02,
            0x01,
            0x00,
            0x08,
            0x00,
            0x01,
            0x03,
            0x00,
            0x00,
            0x07,
            0x01,
        ]
        self.config_reg = 0x63

        self.wip = False
        self.wel = False
        self.bp0 = False
        self.bp1 = False
        self.bp2 = False
        self.e_err = False
        self.p_err = False
        self.srwd = False

        super().__init__(bus)
        # We need to detect the clock frquency to that we can generate delays 
        # during the erase cycles that a significant enough but not onerous either
        # multiple so the detected sclk are used as the measure
        self.time_delta = 1000000000
        start_soon(
            self.detect_clk(
                self._sclk, "sclk", wait_clk_cnt=3
            )
        )

    @property
    def status(self):
        val = 0
        val |= int(self.wip) << 0
        val |= int(self.wel) << 1
        val |= int(self.bp0) << 2
        val |= int(self.bp1) << 3
        val |= int(self.bp2) << 4
        val |= int(self.e_err) << 5
        val |= int(self.p_err) << 6
        val |= int(self.srwd) << 7
        return val

    async def detect_clk(
        self, clk, clk_name="", wait_start=400, wait_clk_cnt=1
    ):
        test_clk = clk
        await Timer(wait_start, "ns")
        for i in range(wait_clk_cnt):
            await RisingEdge(test_clk)
        t0 = get_sim_time("fs")
        await FallingEdge(test_clk)
        t1 = get_sim_time("fs")
        await RisingEdge(test_clk)
        t2 = get_sim_time("fs")
        self.time_delta = t2 - t0
        test_clk_freq = 1000000000 / self.time_delta
        self.log.info(f"Detected Clock frequency {clk_name}: {test_clk_freq:.2f} MHz")

    async def write_in_progress(self, sclk_cnt=256):
        self.wip = 1
        delay = int(sclk_cnt * (8 * self.time_delta) / 1000000)
        self.log.debug(f"delay -> {delay} ns")
        await Timer(delay, "ns")
        self.wip = 0

    async def _shift(self, num_bits: int, tx_word: Optional[int] = None) -> int:
        """Shift in data on the MOSI signal. Shift out the tx_word on the MISO signal.

        Args:
            num_bits: the number of bits to shift
            tx_word: the word to be transmitted on the wire

        Returns:
            the received word on the MOSI line
        """
        rx_word = 0

        frame_end = (
            RisingEdge(self._cs)
            if self._config.cs_active_low
            else FallingEdge(self._cs)
        )

        #         if tx_word is not None:
        #             self.log.info(f"tx 0x{tx_word:02x}")
        for k in range(num_bits):
            if not self._config.cpha:
                if tx_word is not None:
                    self._miso.value = bool(tx_word & (1 << (num_bits - 1 - k)))
                else:
                    self._miso.value = self._config.data_output_idle

            # If both events happen at the same time, the returned one is indeterminate, thus
            # checking for cs = 1
            if 10 == k:
                await Edge(self._sclk)
            else:
                if (
                    await First(Edge(self._sclk), frame_end)
                ) == frame_end or self._cs.value == 1:
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
                if k == num_bits - 1:
                    break

            # do the opposite of what was done on the first edge
            if (
                await First(Edge(self._sclk), frame_end)
            ) == frame_end or self._cs.value == 1:
                raise SpiFrameError("End of frame in the middle of a transaction")

            if self._config.cpha:
                rx_word |= int(self._mosi.value.integer) << (num_bits - 1 - k)

        # Need to realign the phase before starting the next one
        if not self._config.cpha:
            await Edge(self._sclk)
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
        self.active_write = False
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
            #             print(array)
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
            if not self.wip:
                self.wel = True
                self.log.info(f"Enable Write")
        elif Commands.WRDI.value == command:
            pass
        elif Commands.PP.value == command:
            address = int(await self._shift(24))
            self.index = address
            array = self._mem
            txn = True
            if self.wel:
                self.active_write = True
        elif Commands.BE.value == command or Commands.BE2.value == command:
            if self.wel:
                self.active_write = True
                self.log.info(f"Bulk Erasing Flash")
                self._mem.erase()
                start_soon(self.write_in_progress())
        elif Commands.SE.value == command:
            address = int(await self._shift(24))
            if self.wel:
                self.active_write = True
                self.log.info(f"Sector Erasing Flash: 0x{address:08x}")
                self._mem.erase(address, 65536)
                start_soon(self.write_in_progress(64))
        else:
            raise Exception(f"Unimplemented command {Commands(command).name}")

        #         expected_bits = 8*len()
        if txn:
            while True:
                if self.active_write:
                    tx_word = 0xFF
                else:
                    tx_word = array[self.index]
                try:
                    x = await self._shift(8, tx_word=tx_word)
                    content = int(x)
                    if self.wel and not self.wip:
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
            if self.wel:
                self.log.info(f"Disable Write")
            self.wel = False

        #         # end of frame
        #         if await First(frame_end, RisingEdge(self._sclk)) != frame_end:
        #             raise SpiFrameError("S25FL: clocked more than 40 bits")

        if bool(self._sclk.value):
            raise SpiFrameError("S25FL: sclk should be low at chip select edge")
