# pyrf imports
from tkinter import N
from pyrf.devices.thinkrf import WSA
from pyrf.sweep_device import SweepDevice
from pyrf.util import capture_spectrum
from pyrf.util import compute_usable_bins
from pyrf.sweep_device import SweepDevice

# qcodes imports
from qcodes.instrument.base import Instrument
from qcodes.instrument.parameter import ParameterWithSetpoints, Parameter, ArrayParameter
from qcodes.dataset.measurements import Measurement
from qcodes.utils.validators import Numbers, Arrays, Enum

# general imports
import numpy as np
from typing import Sequence, Union, Any

class Setpoints(Parameter):
    """
    Setpoints parameter
    """
    def __init__(self, startpar, stoppar, npointspar, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._startpar = startpar
        self._stoppar = stoppar
        self._npointspar = npointspar

    def get_raw(self):
        npts = self._npointspar()
        start = self._startpar()
        stop = self._stoppar()
       
        return np.linspace( start, stop, npts )
      

class SpectrumArray(ParameterWithSetpoints):
    '''
    Generates an array of noise spectra data with 
    frequency setpoints using capture_sweep_device
    '''
    def __init__(   self, 
                    name: str,
                    instrument: 'R5500',
                    label: str,
                    unit: str,
                    **kwargs    ) -> None:
        super().__init__(   name, instrument=instrument,
                            label=label, unit=unit, 
                            **kwargs)

    def get_raw(self):
        sa = self.root_instrument
        sa.get_npoints()
        return sa._acquired_data['spectra']


class R5500(Instrument):
    ## wrapper around the pyRF API to use R550 with QCoDes
    def __init__(self,
                 name: str,
                 address: str,
                 **kwargs: Any) -> None:
        super().__init__(name, **kwargs)
        
        self.dut = WSA()
        self.dut.connect(address)
        self.dut.request_read_perm()

        self.sweepdevice = SweepDevice(self.dut)

        # Basic settings
        self._rfe_mode = 'SH'
        self._f_start = 6e9
        self._f_stop = 50e6
        self._rbw = 5e3
        self._gain = 'high'
        self._attenuation = 0
        self._average = 1
        self._decimation = 1
        self._reflevel = 0

        self._freqlist = []
        self._spectralist = []

        self._acquired_data = None

        self.add_parameter('rfe_mode',
                                unit = '',
                                initial_value= 'SH',
                                label = 'Input Mode',
                                get_cmd = self.dut.rfe_mode,
                                set_cmd = self.dut.rfe_mode,
                                get_parser = str)
        
        self.add_parameter('attenuation',
                                unit = 'dB',
                                initial_value = 0.0,
                                label = 'attenuation',
                                get_cmd = self.dut.attenuator,
                                set_cmd = self.dut.attenuator,
                                get_parser = float,)

        self.add_parameter('gain',
                                unit = '',
                                label = 'gain',
                                get_cmd = self.dut.psfm_gain,
                                set_cmd = self.dut.psfm_gain,
                                get_parser = str)
        
        self.add_parameter('average',
                                unit = '',
                                label = 'average',
                                get_cmd = self.average,
                                set_cmd = self.average,
                                get_parser = int)

        self.add_parameter('rbw',
                                unit = 'Hz',
                                label = 'resolution bandwidth',
                                get_cmd = self.rbw,
                                set_cmd = self.rbw ,
                                get_parser = float)


        self.add_parameter('f_start',
                                unit='Hz',
                                label='fstart',
                                get_cmd= self.f_start,
                                set_cmd= self.f_start,
                                get_parser = float)

        self.add_parameter('f_stop',
                                unit='Hz',
                                label='fstop',
                                get_cmd = self.f_stop,
                                set_cmd= self.f_stop,
                                get_parser = float)

        self.add_parameter('n_points',
                                unit='',
                                get_cmd= self.get_npoints,
                                set_cmd= '',
                                get_parser = int)
        
        self.add_parameter('freq_axis',
                                unit='Hz',
                                label='Frequency',
                                parameter_class=Setpoints,
                                startparam=self.f_start,
                                stopparam=self.f_stop,
                                xpointsparam=self.n_points,
                                vals=Arrays(shape=(self.n_points.get_latest,)))

        self.add_parameter('spectrum',
                                unit='dBm',
                                setpoints=(self.freq_axis,),
                                label='Noise power',
                                parameter_class=SpectrumArray,
                                vals=Arrays(shape=(self.n_points.get_latest,)))


    def get_npoints(self):
        '''

        '''             
        fstart = self.fstart
        fstop = self.fstop
        rbw = self.rbw
        device_settings = {'attenuator' : self._attenuation}
        mode = self.rfe_mode
        average = self.average

        sweepdev = SweepDevice(self.dut)

        fstart, fstop, spectrum = sweepdev.capture_power_spectrum(fstart=fstart,
                               fstop=fstop,
                               rbw=rbw,
                               device_settings=device_settings,
                               mode=mode,
                               average = average)
        
        self._acquired_data = dict({'fstart':fstart,
                                'fstop' : fstop,
                                'spectrum' : spectrum})
        self.f_start(fstart)
        self.f_stop(fstop)

        return (len(spectrum),)
                    
    @property
    def f_start( self, f_start=None ):
        if f_start is None:
            return self._f_start
        self._f_start = f_start

    @property
    def f_stop( self, f_stop=None ):
        if f_stop is None:
            return self._f_stop
        self._f_start = f_stop

    @property
    def average( self, average = None ):
        if average is None:
            return self._average
        self._average = average

    @property
    def rbw(self, rbw = None):
        if rbw is None:
            return self._rbw
        self._rbw = rbw


