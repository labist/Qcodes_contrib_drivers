import numpy as np
from typing import Sequence, Union, Any

# from qcodes.instrument.base import Instrument
from qcodes.dataset.measurements import Measurement
from qcodes.utils.validators import Numbers, Arrays

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
        npoints = self.root_instrument.x_points.get_latest()
        return np.random.rand(npoints)


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