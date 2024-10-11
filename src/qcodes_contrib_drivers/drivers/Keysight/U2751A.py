import time
import typing as tp
from itertools import product

from qcodes import VisaInstrument, InstrumentChannel
import qcodes.validators as vals

class U2751A(VisaInstrument):
    """
    QCoDeS driver for Agilent U2751A USB Modular switch
    """
    def __init__(self, name: str, address: str, relay_delay: float, **kwargs): 
        """
        QCoDeS driver for Agilent U2751A USB Modular switch

        Args:
            name: name of instrument
            address: visa address
            relay_delay: delay in seconds after any relay flip
        """
        super().__init__(name=name, address=address, terminator='\n', **kwargs)

        for r, c in product(range(1, 5), range(1, 9)):
            cnumber = f'{r}0{c}'
            conn = Connection(self, cnumber)
            self.add_submodule(f'c{cnumber}', conn)
        
        self.relay_delay = relay_delay

    def ask(self, query: str):
        """
        Query instrument. Override *IDN? because it returns non-ascii characters
        """
        if query == "*IDN?":
            return 'AGILENT TECHNOLOGIES, U2751A'
        else:
            return super().ask(query)
        
    def open_all(self):
        """
        Opens all connections
        """
        for _, conn in self.submodules.items():
            if conn.state() == 'CLOSED':
                conn.open()
                time.sleep(self.relay_delay)

    def close_by_inds(self, coord: tp.Sequence[tp.Tuple[int, int]]):
        """
        Alternative method for closing connection. Closes one connection
        """
        if (conn := self.submodules[f'c{coord[0]}0{coord[1]}']).state() == 'OPEN':
            conn.close()
            time.sleep(self.relay_delay)
        
class Connection(InstrumentChannel):

    def __init__(self, parent:U2751A, number:str):
        """
        Connection for U2751A. Supply parameters for open, close, and cycles

        Args:
            parent: parent instrument
            number: three-digit U2751A connection name. e.g. 101
        """
        super().__init__(parent, f'c{number}')
        self.number = number
        self.add_parameter(name='state',
                           get_cmd=self._get_state,
                           set_cmd=self._set_state,
                           vals=vals.Enum('OPEN', 'CLOSED'))
        self.add_parameter(name='cycles',
                           get_cmd=self._get_cycles)

    def close(self):
        """
        Close this connection
        """
        self.state('CLOSED')

    def open(self):
        """
        Open this connection
        """
        self.state('OPEN')

    def _get_cycles(self):
        cycles = self.parent.ask(f"DIAG:REL:CYCL? (@{self.number})")
        return int(cycles)
    
    def _get_state(self):
        """
        Get current state. Returns OPEN or CLOSED 
        """
        if self.parent.ask(f"ROUTE:OPEN? (@{self.number})") == '1':
            return 'OPEN'
        else:
            return 'CLOSED'
        
    def _set_state(self, state) :
        if state == 'OPEN':
            self.parent.write(f"ROUTE:OPEN (@{self.number})")
        elif state == 'CLOSED':
            self.parent.write(f"ROUTE:CLOSE (@{self.number})")