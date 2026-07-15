from typing import Any
from qcodes.instrument import VisaInstrument
from qcodes.utils.validators import Numbers, Enum
import pyvisa
from pyvisa.constants import StopBits, Parity

class SRDC205(VisaInstrument):
    """
    QCodes driver for Stanford Research Systems DC205 Voltage Source.
    
    This driver communicates with the DC205 via USB serial interface
    at a fixed baud rate of 115,200.
    """

    def __init__(
        self,
        name: str,
        address: str,
        baud_rate: int = 115200,
        data_bits: int = 8,
        stop_bits: int = 1,
        parity: str = 'none',
        timeout: float = 5000,
        **kwargs: Any
    ):
        """
        Initialize the DC205 driver.

        Args:
            name: Instrument name
            address: VISA address (e.g., 'ASRL3::INSTR')
            baud_rate: Serial baud rate (default: 115200, fixed for DC205)
            data_bits: Number of data bits (default: 8)
            stop_bits: Number of stop bits (default: 1)
            parity: Parity setting - 'none', 'odd', or 'even' (default: 'none')
            timeout: Communication timeout in milliseconds (default: 5000)
            **kwargs: Additional arguments passed to VisaInstrument
        """
        super().__init__(name, address, **kwargs)

        # Map integer stop_bits to enum
        stop_bits_map = {
            1: StopBits.one,
            1.5: StopBits.one_and_a_half,
            2: StopBits.two
        }
        
        # Map parity string to enum
        parity_map = {
            'none': Parity.none,
            'odd': Parity.odd,
            'even': Parity.even
        }
        
        # Configure serial port parameters
        self.visa_handle.baud_rate = baud_rate
        self.visa_handle.data_bits = data_bits
        self.visa_handle.stop_bits = stop_bits_map.get(stop_bits, StopBits.one)
        self.visa_handle.parity = parity_map.get(parity, Parity.none)
        self.visa_handle.timeout = timeout

        # Set line terminators
        self.visa_handle.write_termination = '\r\n'
        self.visa_handle.read_termination = '\r\n'

        # Add voltage parameter
        self.add_parameter(
            'voltage',
            label='Output Voltage',
            unit='V',
            get_cmd='VOLT?',
            set_cmd='VOLT {}',
            get_parser=float,
            vals=Numbers(min_value=-100, max_value=100),  # Adjust range as needed
            docstring='Output voltage in volts'
        )

        # Add range parameter. you have to turn off output to set range!!
        self.add_parameter(
            'range',
            label='Output Range',
            get_cmd='RNGE?',
            set_cmd = self._set_range, # set the range check for error
            # set_cmd='RNGE {}',
            # get_parser=float,
            # vals=Numbers(min_value=-20, max_value=20),  # Adjust range as needed
            docstring='Output voltage range. you have to turn off output to set range!!'
        )

        # Add output on/off parameter
        self.add_parameter(
            'output',
            label='Output State',
            get_cmd='SOUT?',
            set_cmd='SOUT {}',
            val_mapping={'on': 1, 'off': 0},
            docstring='Turn output on or off'
        )

        # Connect and identify
        self.connect_message()

    def _set_range(self, range: int):
        """
        set range and check for error
        """
        self.write(f'RNGE {range}')
        lexe = int(self.ask_raw('LEXE?'))
        if lexe != 0: # something bad, read the manual
            raise Exception(f"Last execution error code {lexe}. Try turning output off.")
        
    def get_idn(self) -> dict:
        """
        Override get_idn to properly parse the DC205 response.
        
        Returns:
            Dictionary with vendor, model, serial, and firmware version
        """
        response = self.ask('*IDN?')
        parts = response.split(',')
        
        idn_dict = {
            'vendor': parts[0] if len(parts) > 0 else '',
            'model': parts[1] if len(parts) > 1 else '',
            'serial': parts[2] if len(parts) > 2 else '',
            'firmware': parts[3] if len(parts) > 3 else ''
        }
        return idn_dict

    def reset(self) -> None:
        """Reset the instrument to default state."""
        self.write('*RST')

    def clear_status(self) -> None:
        """Clear the instrument status."""
        self.write('*CLS')

    def get_status(self) -> str:
        """
        Get the instrument status register.
        
        Returns:
            Status register value as string
        """
        return self.ask('*STB?')

    def set_voltage_ramp(self, target_voltage: float, rate: float) -> None:
        """
        Set voltage with a ramp rate.
        
        Args:
            target_voltage: Target voltage in volts
            rate: Ramp rate in V/s
        """
        # Note: Adjust these commands based on actual DC205 SCPI commands
        self.write(f'VOLT {target_voltage}')
        # If DC205 supports ramp rate, add command here
        # self.write(f'RAMP {rate}')
