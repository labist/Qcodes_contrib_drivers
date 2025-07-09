import numpy as np
from typing import Sequence, Union, Any

# from qcodes.instrument.base import Instrument
from qcodes.dataset.measurements import Measurement
from qcodes.utils.validators import Numbers, Arrays, Enum

from qcodes.instrument.parameter import ParameterWithSetpoints, Parameter
from qcodes import VisaInstrument

from time import sleep

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
        # i think we can access the resource with somethign like self.instrument.visa_handle
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

class USB_SA124B(VisaInstrument):

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
        self.add_parameter('f_start',
                           unit='Hz',
                           label='f start',
                           vals=Numbers(0,13e9),
                           get_cmd=":SENSe:FREQuency:STARt?",
                           set_cmd=":SENSe:FREQuency:STARt {}",
                           get_parser=float )

        self.add_parameter('f_stop',
                           unit='Hz',
                           label='f stop',
                           vals=Numbers(0,13e9),
                           get_cmd=":SENSe:FREQuency:STOP?",
                           set_cmd=":SENSe:FREQuency:STOP {}",
                           get_parser=float )

        self.add_parameter('f_center',
                        unit='Hz',
                        label='f center',
                        vals=Numbers(0,13e9),
                        get_cmd=":SENSe:FREQuency:CENTER?",
                        set_cmd=":SENSe:FREQuency:CENTER {}",
                        get_parser=float )

        self.add_parameter('f_span',
                        unit='Hz',
                        label='f span',
                        vals=Numbers(0,13e9),
                        get_cmd=":SENSe:FREQuency:SPAN?",
                        set_cmd=":SENSe:FREQuency:SPAN {}",
                        get_parser=float )

        self.add_parameter('rbw',
                        unit='Hz',
                        label='res. bandwidth',
                        get_cmd=":SENSe:BANDwidth:RESolution?",
                        set_cmd=":SENSe:BANDwidth:RESolution {}",
                        get_parser=float )

        self.add_parameter('vbw',
                        unit='Hz',
                        label='vid. bandwidth',
                        get_cmd=":SENSe:BANDwidth:VIDeo?",
                        set_cmd=":SENSe:BANDwidth:VIDeo {}",
                        get_parser=float )

        self.add_parameter('avg',
                        unit='',
                        label='averages',
                        get_cmd=":TRACe:AVERage:COUNt?",
                        set_cmd=":TRACe:AVERage:COUNt {:d}",
                        get_parser=int )
        
        self.add_parameter('ref_lvl',
                        label='Reference power',
                        unit='dBm',
                        get_cmd=":SENSe:POWer:RLEVel?",
                        set_cmd=":SENSe:POWer:RLEVel {:f}",
                        get_parser=int )

        self.add_parameter('gain',
                        label='Gain',
                        unit='level',
                        initial_value=-1,
                        get_cmd=":SENSe:POWer:GAIN?",
                        set_cmd=":SENSe:POWer:GAIN {:d}",
                        get_parser=int )

        self.add_parameter('atten',
                        label='Attenuation',
                        unit='level',
                        initial_value=-1,
                        get_cmd=":SENSe:POWer:ATTENuation?",
                        set_cmd=":SENSe:POWer:ATTENuation {:d}",
                        get_parser=int )

        self.add_parameter('preamp',
                        label='Preamp',
                        unit='level',
                        initial_value=-1,
                        get_cmd=":SENSe:POWer:PREAMP?",
                        set_cmd=":SENSe:POWer:PREAMP {:d}",
                        get_parser=int )

        self.add_parameter('type',
                        unit='',
                        label='averages',
                        get_cmd=":TRACe:TYPE?",
                        set_cmd=":TRACe:TYPE {}",
                        vals=Enum('OFF', 'WRIT', 'AVER', 'MAX', 'MIN', 'MINMAX' ) )
 
        # x_ are used for computing trace x spacing
        self.add_parameter('x_start',
                        unit='',
                        label='x start',
                        get_cmd=":TRACe:XSTARt?",
                        set_cmd="",
                        get_parser=float )

        self.add_parameter('x_inc',
                        unit='',
                        label='x increment',
                        get_cmd=":TRACe:XINCrement?",
                        set_cmd="",
                        get_parser=float )

        self.add_parameter('x_points',
                           unit='',
                           initial_value=10,
                           vals=Numbers(1,1e9),
                           get_cmd=":TRACe:POINts?",
                           set_cmd="",
                           get_parser=int )

        self.add_parameter('freq_axis',
                           unit='Hz',
                           label='Freq',
                           parameter_class=GeneratedSetPoints,
                           startparam=self.x_start,
                           incparam=self.x_inc,
                           xpointsparam=self.x_points,
                           vals=Arrays(shape=(self.x_points.get_latest,)))

        self.add_parameter('spectrum',
                   unit='dBm',
                   setpoints=(self.freq_axis,),
                   label='Noise power',
                   parameter_class=SpectrumArray,
                   vals=Arrays(shape=(self.x_points.get_latest,)))

        self.add_parameter('ch_pwr',
                        unit='dBm',
                        label='Channel Power',
                        get_cmd=":SENSe:CHPower:CHPower?",
                        set_cmd="",
                        get_parser=float )

        self.add_parameter('ch_pwr_state',
                        unit='',
                        label='Channel Power State',
                        get_cmd=":SENSe:CHPower:STATe?",
                        set_cmd=":SENSe:CHPower:STATe {}",
                        vals=Enum('ON', 'OFF', '1', '0' ) )

        self.add_parameter('ch_pwr_width',
                unit='Hz',
                label='Channel Power Width',
                get_cmd=":SENSe:CHPower:WIDTH?",
                set_cmd=":SENSe:CHPower:WIDTH {}",
                get_parser=float )

        self.add_parameter('ref_osc_source',
                        unit='',
                        label='Reference Oscillator',
                        get_cmd=":SENSe:ROSC:SOURce?",
                        set_cmd=":SENSe:ROSC:SOURce {}",
                        vals=Enum('INT', 'EXT', 'OUT') )

        self.add_parameter('dev_isactive',
                        unit='',
                        label='Device Active',
                        get_cmd=":SYST:DEV:ACT?" )

        self.add_parameter('dev_list',
                        unit='',
                        label='Device List',
                        get_cmd=":SYST:DEV:LIST?" )
        
        self.add_parameter('connect',
                        unit='',
                        label='Device Connect',
                        get_cmd=":SYST:DEV:CON?",
                        set_cmd=":SYST:DEV:CON? {}",
                        get_parser=str )


    def clear( self ) :
        ''' clear the trace
        '''
        self.write( ':TRACe:CLEar' )

    def reconnect( self, id=None ) :
        '''
        reconnects to the device or to the provided id
        id : integer
        '''
        self.ask(':SYST:DEV:ACT?')
        sleep(0.1)
        if id is None:
            if self.ask(':SYST:DEV:ACT?') == '0':
                dev_id = ''
                for i in range(5):
                    dev_id = self.ask(':SYST:DEV:LIST?')
                    if len(dev_id) > 2:
                        break
                    sleep(0.1)
                self.write(':SYST:DEV:CON? '+dev_id)
                
        if id is not None:
            self.write(':SYST:DEV:CON? '+str(id))
        sleep(7)
        
        return self.ask(':SYST:DEV:ACT?')