from itertools import product
from functools import partial

from qcodes import VisaInstrument, InstrumentChannel
import qcodes.validators as vals

class U2571A(VisaInstrument):
    """
    QCoDeS driver for Agilent U2571A USB Modular switch
    """

    def __init__(self, name:str, address:str, **kwargs): 
        """
        QCoDeS driver for Agilent U2571A USB Modular switch

        Args:
            name: name of instrument
            address: visa address
        """
        super().__init__(name=name, address=address, terminator='\n', **kwargs)

        for r,c in product(range(1,5), range(1,9)):
            cnumber = f'{r}0{c}'
            channel = Connection(self, cnumber)
            self.add_submodule(f'c{cnumber}', channel)

    def ask(self, query:str):
        """
        Query instrument. Override *IDN? because it returns non-ascii characters
        """
        if query == "*IDN?":
            return 'AGILENT TECHNOLOGIES, U2571A'
        else:
            return super().ask(query)
        
class Connection(InstrumentChannel) :

    def __init__(self, parent:U2571A, number:str):
        """
            Connection for U2571A. Supply parameters for open, close, and cycles
            Args:
                parent: parent instrument
                number: three-digit U2571A channel name. e.g. 101
        """

        super().__init__(parent, f'c{number}')
        self.number = number
        self.add_parameter(
            'state',
            get_cmd=self._get_state,
            set_cmd=self._set_state,
            vals=vals.Enum('OPEN', 'CLOSED')
        )

        self.add_parameter(
            'cycles',
            get_cmd=self._get_cycles
        )

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
    
    def _get_state(self) :
        """
            Get current state. Returns OPEN or CLOSED 
        """
        
        if self.parent.ask(f"ROUTE:OPEN? (@{self.number})"):
            return 'OPEN'
        else:
            return 'CLOSED'
        
    def _set_state(self, state) :
        if state == 'OPEN':
            self.parent.write(f"ROUTE:OPEN (@{self.number})")
        elif state == 'CLOSED':
            self.parent.write(f"ROUTE:CLOSE (@{self.number})")