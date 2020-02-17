import numpy as np
from typing import Sequence, Union, Any

# from qcodes.instrument.base import Instrument
from qcodes.dataset.measurements import Measurement
from qcodes.utils.validators import Numbers, Arrays

from qcodes.instrument.parameter import ParameterWithSetpoints, Parameter
from qcodes import VisaInstrument

class GeneratedSetPoints(Parameter):
    """
    A parameter that generates a setpoint array from start, stop and num points
    parameters.
    """
    def __init__(self, startparam, stopparam, numpointsparam, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._startparam = startparam
        self._stopparam = stopparam
        self._numpointsparam = numpointsparam

    def get_raw(self):
        return np.linspace(self._startparam(), self._stopparam(),
                              self._numpointsparam())

class DummyArray(ParameterWithSetpoints):

    def get_raw(self):
        npoints = self.root_instrument.n_points.get_latest()
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
                           set_cmd=":SENSe:FREQuency:STARt {}" )

        # self.add_parameter('f_stop',
        #                    unit='Hz',
        #                    label='f stop',
        #                    vals=Numbers(1,1e3),
        #                    get_cmd=None,
        #                    set_cmd=None)

        # self.add_parameter('n_points',
        #                    unit='',
        #                    initial_value=10,
        #                    vals=Numbers(1,1e3),
        #                    get_cmd=None,
        #                    set_cmd=None)

        # self.add_parameter('freq_axis',
        #                    unit='Hz',
        #                    label='Freq Axis',
        #                    parameter_class=GeneratedSetPoints,
        #                    startparam=self.f_start,
        #                    stopparam=self.f_stop,
        #                    numpointsparam=self.n_points,
        #                    vals=Arrays(shape=(self.n_points.get_latest,)))

        # self.add_parameter('spectrum',
        #            unit='dBm',
        #            setpoints=(self.freq_axis,),
        #            label='Spectrum',
        #            parameter_class=DummyArray,
        #            vals=Arrays(shape=(self.n_points.get_latest,)))