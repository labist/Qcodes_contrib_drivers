import numpy as np
from typing import Any

from qcodes import VisaInstrument, validators as vals
from qcodes.utils.helpers import create_on_off_val_mapping


class APSIN20G(VisaInstrument):
    
    def __init__(self, name: str, address: str, **kwargs: Any) -> None:
        super().__init__(name, address, terminator='\n', **kwargs)

        self.add_parameter('output',
                           label='RF output',
                           get_cmd=':OUTPut1?', # 1 = Single channel device
                           set_cmd=':OUTPut {}',
                           val_mapping=create_on_off_val_mapping(on_val='1',
                                                                 off_val='0'))
        # our option 100k - 20G
        self.add_parameter(name='frequency',
                           label='$f_{\\mathrm{AP}}$',
                           unit='Hz',
                           get_cmd=':FREQuency?',
                           set_cmd=':FREQuency {:.3f}',
                           get_parser=float,
                           vals=vals.Numbers(100e3, 20e9))
        
        # our option PE3 -90 -> 15 dBm
        self.add_parameter(name='power',
                           label='$P_{\\mathrm{AP}}$',
                           unit='dBm',
                           get_cmd='POWer?',
                           set_cmd='POWer {:.2f}',
                           get_parser=float,
                           vals=vals.Numbers(-90, 15))

        self.add_parameter(name='phase',
                           label='$\\phi_{\\mathrm{AP}}$',
                           unit='rad',
                           get_cmd=':PHASe?',
                           set_cmd=':PHASe {:.9f}',
                           get_parser=float,
                           vals=vals.Numbers(0, 2*np.pi))

        # Auxilary phase parameter which uses nonnative deg units
        self.add_parameter(name='phase_deg',
                           label='$\\phi_{\\mathrm{AP}}$',
                           unit='deg',
                           get_cmd=':PHASe?',
                           set_cmd=lambda ph:
                               self.write_raw(f':PHASe {ph / 180 * np.pi:.9f}'),
                           get_parser=lambda ph:
                               np.round((float(ph) / np.pi) % 1 * 180, 7),
                           vals=vals.Numbers(0, 360))

        self.add_parameter('display_enabled',
                           label='Display Enabled',
                           get_cmd=':DISPlay:ENABle?',
                           set_cmd=':DISPlay:ENABle {}',
                           val_mapping=create_on_off_val_mapping(on_val='1',
                                                                 off_val='0'))
        
        self.add_parameter('ref_osc_source',
                           label='Reference Oscillator Source',
                           get_cmd='ROSCillator:SOURce?',
                           set_cmd='ROSCillator:SOURce {}',
                           vals=vals.Enum('INT', 'EXT', 'int', 'ext'))
        
        # Frequency of the external reference AnaPico uses
        self.add_parameter('ref_osc_external_freq',
                           label='Reference Oscillator External Frequency',
                           get_cmd='ROSCillator:EXTernal:FREQuency?',
                           set_cmd='ROSCillator:EXTernal:FREQuency {}',
                           get_parser=float,
                           vals=vals.Numbers(1e6, 250e6))
        
        # Frequency of the external reference AnaPico outputs
        self.add_parameter('ref_osc_output_freq',
                           label='Reference Oscillator Output Frequency',
                           get_cmd='ROSC:OUTPut:FREQuency?',
                           set_cmd='ROSC:OUTPut:FREQuency {}',
                           get_parser=float,
                           vals=vals.Enum(10e6, 100e6))

        self.add_function('reset', call_cmd='*RST')
        self.add_function('run_self_tests', call_cmd='*TST?')

        self.connect_message()