# pyrf imports
from tkinter import N
from pyrf.devices.thinkrf import WSA
from pyrf.sweep_device import SweepDevice
from pyrf.util import capture_spectrum
from pyrf.util import compute_usable_bins
from pyrf.sweep_device_dpmod import SweepDevice

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
        sa = self.root_instrument
        if sa._acquired_data is not None:
            npts = sa._acquired_data['npts']
        else:
            npts = self._npointspar()
        start = self._startpar()
        stop = self._stoppar()
       
        return np.linspace( start, stop, npts )
      

class SpectrumArray(ParameterWithSetpoints):
    '''
    Generates an array of noise spectra data with 
    frequency setpoints using capture_sweep_device
    '''
    def get_raw(self):
        sa = self.root_instrument
        sa.n_points()
        return sa._acquired_data['spectrum']


class R5500(Instrument):
    ## wrapper around the pyRF API to use R550 with QCoDes
    def __init__(self,
                 name: str,
                 address: str,
                 **kwargs: Any) -> None:
        super().__init__(name, **kwargs)
        
        self.dut = WSA()
        self.addr = address
        self.dut.connect(address)
        self.dut.request_read_perm()

        # Basic settings
        self._rfemode = 'SH'
        self._fstart = 5e9
        self._fstop = 6e9
        self._rbw = 5e3
        self._gain = 'high'
        self._attenuation = 0
        self._average = 10
        self._decimation = 1
        self._reflevel = 0
        self.triggered = False

        self._acquired_data = None

        self.add_parameter('rfe_mode',
                                unit = '',
                                initial_value= 'SH',
                                label = 'Input Mode',
                                get_cmd = self.get_rfe_mode,
                                set_cmd = self.set_rfe_mode,
                                get_parser = str)
        
        self.add_parameter('attenuation',
                                unit = 'dB',
                                initial_value = 0.0,
                                label = 'attenuation',
                                get_cmd = self.get_attenuation,
                                set_cmd = self.set_attenuation,
                                get_parser = float,)

        self.add_parameter('gain',
                                unit = '',
                                label = 'gain',
                                get_cmd = self.get_psfm_gain,
                                set_cmd = self.set_psfm_gain,
                                get_parser = str)
        
        self.add_parameter('average',
                                unit = '',
                                label = 'average',
                                get_cmd = self.get_average,
                                set_cmd = self.set_average,
                                get_parser = int)

        self.add_parameter('rbw',
                                unit = 'Hz',
                                label = 'resolution bandwidth',
                                get_cmd = self.get_rbw,
                                set_cmd = self.set_rbw ,
                                get_parser = float)


        self.add_parameter('f_start',
                                unit='Hz',
                                label='fstart',
                                get_cmd= self.get_fstart,
                                set_cmd= self.set_fstart,
                                get_parser = float)

        self.add_parameter('f_stop',
                                unit='Hz',
                                label='fstop',
                                get_cmd = self.get_fstop,
                                set_cmd= self.set_fstop,
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
                                startpar=self.f_start,
                                stoppar=self.f_stop,
                                npointspar=self.n_points,
                                vals=Arrays(shape=(self.n_points.get_latest,)))

        self.add_parameter('spectrum',
                                unit='dBm',
                                setpoints=(self.freq_axis,),
                                label='Noise power',
                                parameter_class=SpectrumArray,
                                vals=Arrays(shape=(self.n_points.get_latest,)))


    def get_npoints(self):
        '''
        Configs the sweep and collects the data. Returns length of data for
        generating the setpoints.
        '''             
        fstart = self.f_start()
        fstop = self.f_stop()
        rbw = self.rbw()
        device_settings = { 'attenuator' : self.attenuation() }
        mode = self.rfe_mode()
        average = self.average()

        self.dut.reset()
        self.dut.psfm_gain(self._gain)
        self.dut.spp(1024)
        self.dut.ppb(4)
        self.dut.pll_reference('EXT')

        sweepdev = SweepDevice(self.dut)

        sweepdev.real_device.flush_captures()
        fstart, fstop, spectrum = sweepdev.capture_power_spectrum(fstart=fstart,
                               fstop=fstop,
                               rbw=rbw,
                               device_settings=device_settings,
                               mode=mode,
                               average = average)
        
        self._acquired_data = dict({'fstart':fstart,
                                'fstop' : fstop,
                                'spectrum' : spectrum,
                                'npts' : len(spectrum) })
        self.f_start(fstart)
        self.f_stop(fstop)

        self.dut.sweep_stop()
        self.dut.abort()
        self.dut.flush_captures()

        print("INVOKED !")

        return len(spectrum)
                    
    def get_fstart( self ):
        return self._fstart

    def set_fstart( self, fstart ):
        self._fstart = fstart

    def get_fstop( self ):
        return self._fstop
        
    def set_fstop( self, fstop ):
        self._fstop = fstop

    def get_average( self ):
        return self._average

    def set_average( self, average ):
        self._average = average

    def get_rbw( self ):
        return self._rbw

    def set_rbw(self, rbw):
        self._rbw = rbw

    def get_rfe_mode( self ):
        return self._rfemode
    
    def set_rfe_mode( self, rfemode ):
        self._rfemode = rfemode
        self.dut.rfe_mode(self._rfemode)

    def get_attenuation( self ):
        return self._attenuation

    def set_attenuation( self, atten ):
        self._attenuation = atten
        self.dut.attenuator( self._attenuation )

    def get_psfm_gain( self ):
        return self._gain

    def set_psfm_gain( self, gain ):
        self._gain = gain
        self.dut.psfm_gain( self._gain )