import logging

from cocotbext.axi import AxiLiteBus
from cocotbext.axi import AxiLiteMaster

class AxiLiteDriver:
    def __init__(self, dut, axil_prefix="s_axi", clk_name="s_aclk", reset_name=None, seednum=None) -> None:
        self.log = logging.getLogger(f"cocotb.AxilDriver")
        self.enable_logging()
        self.length = 4
        if reset_name is None:
            self.axil_master = AxiLiteMaster(AxiLiteBus.from_prefix(dut, axil_prefix), getattr(dut, clk_name))
        else:
            self.axil_master = AxiLiteMaster(AxiLiteBus.from_prefix(dut, axil_prefix), getattr(dut, clk_name), getattr(dut, reset_name))
        self.axil_master.write_if.log.setLevel(logging.WARNING)
        self.axil_master.read_if.log.setLevel(logging.WARNING)

    @property
    def returned_val(self):
        if hasattr(self.read_op, "data"):
            if hasattr(self.read_op.data, "data"):
                return int.from_bytes(self.read_op.data.data, byteorder="little")
            else:
                return int.from_bytes(self.read_op.data, byteorder="little")
        else:
            return int.from_bytes(self.read_op, byteorder="little")

    def enable_logging(self) -> None:
        self.log.setLevel(logging.DEBUG)
    
    def disable_logging(self) -> None:
        self.log.setLevel(logging.WARNING)

    def check_read(self, debug=True):
        if debug:
            self.log.debug(f"Read  0x{self.addr:08x}: 0x{self.returned_val:08x}")
        if not self.returned_val == self.data and not None == self.data:
            raise Exception(
                f"Expected 0x{self.data:08x} doesn't match returned 0x{self.returned_val:08x}"
            )

    async def write(self, addr, data=None, debug=True) -> None:
        self.addr = addr
        if data is None:
            self.data = 0
            for i in range(0, self.length, 4):
                self.data = self.data | (randint(0, 0xffffffff) << i*8)
        else:
            self.data = data
        self.writedata = self.data
        if debug:
            self.log.debug(f"Write 0x{self.addr:08x}: 0x{self.data:0{self.length*2}x}")
        bytesdata = self.data.to_bytes(self.length, "little")
#         #bytesdata = self.data.to_bytes(self.length, 'little')
        await self.axil_master.write(addr, bytesdata)

    async def read(self, addr, data=None, debug=True) -> int:
        self.addr = addr
        self.data = data
        self.read_op = await self.axil_master.read(self.addr, self.length)
        self.check_read(debug)
#         return self.read_op
        return self.returned_val
