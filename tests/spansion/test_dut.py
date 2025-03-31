import logging
from random import randint     
from cocotb import test
from cocotb.triggers import Timer

from interfaces.clkrst import ClkReset
from interfaces.clkrst import Clk

from cocotbext.spi import SpiBus
from cocotbext.spi import SpiConfig
# from cocotbext.spi import SpiMaster
from cocotbext.spi.devices.Spansion.S25FL import S25FL
from cocotbext.spi.devices.Spansion.S25FL import Commands

from interfaces.axilite_wrapper import AxiLiteDriver

class testbench:
    def __init__(self, dut, reset_sense=1, period=10):

        self.cr = ClkReset(dut, period, reset_sense=reset_sense, resetname="rst")
        self.ext_clk = Clk(dut, 3, clkname="ext_spi_clk")
#         self.dut = dut

#         self.bytes = 2
#         self.speed = 25e6
        
        axil_prefix = "s_axi"
        clk_name = "clk"
        
        self.intf = AxiLiteDriver(dut, axil_prefix=axil_prefix, clk_name=clk_name)
        
#         spi_signals = {
#             'sclk': 'sck', 
#             'mosi': 'io0', 
#             'miso': 'io1', 
#             'cs': 'ss',
#         }
        spi_signals = {
            'sclk': 'w_sck_o', 
#             'sclk': 'sck', 
            'mosi': 'w_io0_o', 
            'miso': 'w_io1_i', 
            'cs': 'w_ss_t',
        }
        self.bus = SpiBus(
            dut, 
            sclk_name=spi_signals['sclk'], 
            mosi_name=spi_signals['mosi'], 
            miso_name=spi_signals['miso'], 
            cs_name=spi_signals['cs'],
        )

        self.spi = S25FL(self.bus)
        self.alive = True        


    async def wait_clkn(self, length=1):
            await self.cr.wait_clkn(length)

    async def end_test(self, length=10):
        await self.wait_clkn(length)


    def check_read(self, returned, expected):
        if not expected == returned and expected >= 0:
            raise Exception(
                f"Expected 0x{returned:08x} doesn't match returned 0x{expected:08x}"
            )


    async def first_access(self):
#         self.spi._miso.value = 1
        if not self.alive:
            await self.intf.read(0x00000064)
        self.alive = True

    async def axiqspi_access(self, cmds, index_start=0, debug=False):
        await self.first_access()
        for cmd in cmds:
            await self.intf.write(0x00000068, cmd, debug=debug)
    
        await self.intf.read(0x00000074, debug=True)
        await self.intf.write(0x00000060, 0x00000006, debug=debug)
        rx = []
        for i in range(len(cmds)):
            val = 0x1
            while not 0x0 == val:
                ret_val = await self.intf.read(0x00000064, debug=debug)
                val = ret_val & 0x1
            x = await self.intf.read(0x0000006c, debug=debug)
            rx.append(x)

        await self.intf.write(0x00000060, 0x00000180, debug=debug)
#         if not 0 == index_start:
#             for i in range(index_start, len(cmds)):
#                 print(f"0x{rx[i]:02x}")
        await Timer(self.spi._config.frame_spacing_ns, 'ns')
#         print(rx[index_start:])    
        return rx[index_start:]
#         return rx[4:]

    async def spansion_pp(self, addr : int, data: int, length : int = -1):
        if length < 0:
            length = 1
        if length > 256:
            raise Exception(f"Length is greater than 256: {length}")
        cmds = []
        cmds.append(Commands.PP.value)
        for i in range(3):
            cmds.append((addr>>(16-(8*i))) & 0xff)
        for i in range(length):
            cmds.append((data >> i*8) & 0xff)
#         print(cmds)
        
        await self.axiqspi_access(cmds)
#         return val

    async def spansion_read(self, addr : int, data:int = -1, length : int = 1):
        cmds = []
        cmds.append(Commands.READ.value)
        for i in range(3):
            cmds.append((addr>>(16-(8*i))) & 0xff)
        for i in range(length):
            cmds.append(0xff)
        
        val = await self.axiqspi_access(cmds, 4)
        result = 0
        for i in range(len(val)):
            result += val[i] << (i*8)
#         print(f"{result:x} {data:x}")
        self.check_read(result, data)
        return val

    async def spansion_fastread(self, addr : int, length : int = 1):
        cmds = []
        cmds.append(Commands.FAST_READ.value)
        for i in range(3):
            cmds.append((addr>>(16-(8*i))) & 0xff)
        cmds.append(0xff)
        for i in range(length):
            cmds.append(0xff)
        
        val = await self.axiqspi_access(cmds, 5)
        return val

    async def spansion_rdid(self):
        length = 3
        
        cmds = []
        cmds.append(Commands.RDID.value)
        for i in range(length):
            cmds.append(0xff)
        val = await self.axiqspi_access(cmds, 1, debug=False)
        #print(val)
        return val
        
    async def spansion_wren(self):
        cmds = []
        cmds.append(Commands.WREN.value)
        await self.axiqspi_access(cmds)
        

    async def spansion_wrdi(self):
        cmds = []
        cmds.append(Commands.WRDI.value)
        await self.axiqspi_access(cmds)
        
    async def spansion_rdsr(self, data=-1, length=1):
        cmds = []
        cmds.append(Commands.RDSR.value)
        for i in range(length):
            cmds.append(0xff)
        val = await self.axiqspi_access(cmds, 1)
        print(f"Status: 0x{val[-1]:02x}")
        self.check_read(val[-1], data)
        return val[-1]

    async def spansion_rcr(self, data=-1, length=1):
        cmds = []
        cmds.append(Commands.RCR.value)
        for i in range(length):
            cmds.append(0xff)
        val = await self.axiqspi_access(cmds, 1)
        print(f"Config: 0x{val[-1]:02x}")
        self.check_read(val[-1], data)
        return val[-1]

    async def spansion_wrr(self, status, config=-1):
        length = 2
        
        cmds = []
        cmds.append(Commands.WRR.value)
        cmds.append(status)
        if config >= 0:
            cmds.append(config)
        await self.axiqspi_access(cmds)

    async def spansion_be(self):
        cmds = []
        cmds.append(Commands.BE.value)
        await self.axiqspi_access(cmds)
        


@test()
async def test_fsm_reset(dut):
    tb = testbench(dut, reset_sense=0)
    await Timer(10, 'us')

    ret = await tb.spansion_rdid()
    assert ret[0] == 0x7e
#     print(ret)
    
#     await tb.spansion_read(0x000001, length=2)
# 
# #     await tb.spansion_read(0x000000, length=1)
# # 
# #     await tb.spansion_read(0x000004, length=4)
# # 
# # 
# #     await tb.spansion_wren()
# # 
# #     await tb.spansion_wrdi()
# # 
# #     await tb.spansion_read(0x000002, length=1)
# # 
# #     await tb.spansion_fastread(0x000003, 2)
# #     
# #     await tb.spansion_rdsr()
# #     await tb.spansion_rcr()
# #     
# #     await tb.spansion_wrr(0x75, 0x43)
# #     
# #     await tb.spansion_rdsr(0x75)
# #     await tb.spansion_rcr(0x43)
# 
#     await tb.spansion_read(0x000010, 0xffffffff, length=4)
#     await tb.spansion_pp(0x000010, 0x4971, length=2)
#     await tb.spansion_read(0x000010, 0xffffffff, length=4)
#     await tb.spansion_wren()
#     await tb.spansion_pp(0x000010, 0x43)
#     await tb.spansion_read(0x000010, 0x43, length=1)
#     await tb.spansion_pp(0x000020, 0x98765432, length=4)
#     await tb.spansion_read(0x000020, 0xffffffff, length=4)
#     await tb.spansion_wren()
#     await tb.spansion_pp(0x000020, 0x35461245, length=4)
#     await tb.spansion_read(0x000020, 0x35461245, length=4)
# 
#     await tb.spansion_wren()
#     await tb.spansion_be()
    await tb.spansion_read(0x000020, 0xffffffff, length=4)

    await tb.wait_clkn(20)
