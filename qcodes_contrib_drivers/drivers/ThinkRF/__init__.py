import numpy as np
from typing import Sequence, Union, Any

# from qcodes.instrument.base import Instrument
from qcodes.dataset.measurements import Measurement
from qcodes.utils.validators import Numbers, Arrays, Enum

from qcodes.instrument.parameter import ParameterWithSetpoints, Parameter
from qcodes import VisaInstrument

class GeneratedSetPoints(Parameter):
    """
    A parameter that generates a setpoint array from start, increment, and n_points

                               parameter_class=GeneratedSetPoints,
                           startparam=self.x_start,
                           incparam=self.x_inc,
                           xpointsparam=self.x_points,
    """
    def __init__(self, startparam, incparam, xpointsparam, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._startparam = startparam
        self._incparam = incparam
        self._xpointsparam = xpointsparam

    def get_raw(self):
        start = self._startparam()
        inc = self._incparam()
        npts = self._xpointsparam()
        stop = start + inc * ( npts - 1 )
        return np.linspace( start, stop, npts )

class SpectrumArray(ParameterWithSetpoints):

    def get_raw(self):
        # :TRACe[:DATA]? need to test this live
        # i think we can access the visa resource with somethign like self.instrument.visa_handle
        sa = self.instrument
        visa_handle = sa.visa_handle

        # Disable continuous meausurement operation
        visa_handle.write('INIT:CONT OFF')   
        # visa_handle.write( 'TRAC:TYPE WRIT')
        visa_handle.write( 'TRAC:UPD ON')
        visa_handle.write( 'TRAC:DISP ON')
        # Trigger a sweep, and wait for it to complete
        visa_handle.query(':INIT; *OPC?' )
        data_str = visa_handle.query( ':TRACe:DATA?' )
        visa_handle.write('INIT:CONT ON')   
        return np.fromstring( data_str, sep=',' )

class R550(VisaInstrument):

    def __init__(self,
                 name: str,
                 address: str,
                 **kwargs: Any) -> None:
        super().__init__(name, address, terminator='\n', **kwargs)

        #         # Number of averages (also resets averages)
        # self.add_parameter('averages_enabled',
        #                    label='Averages Enabled',
        #                    get_cmd="SENS:AVER?",
        #                    set_cmd="SENS:AVER {}",
        #                    val_mapping={True: '1', False: '0'})


        self.add_parameter('f_center',
                        unit='Hz',
                        label='f center',
                        vals=Numbers(0,13e9),
                        get_cmd=":SENSe:FREQuency:CENTER?",
                        set_cmd=":SENSe:FREQuency:CENTER {}",
                        get_parser=float )

    def clear( self ) :
        ''' clear the trace
        '''
        self.write( ':TRACe:CLEar' )