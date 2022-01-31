from pyrf.devices.thinkrf import WSA
from pyrf.sweep_device import SweepDevice
from pyrf.util import capture_spectrum
from pyrf.util import compute_usable_bins


import sys
import time
import math

from matplotlib.pyplot import plot, figure, axis, xlabel, ylabel, show
import numpy as np

from typing import Sequence, Union, Any


from qcodes.instrument.base import Instrument
from qcodes.instrument.parameter import ParameterWithSetpoints, Parameter
from qcodes.dataset.measurements import Measurement
from qcodes.utils.validators import Numbers, Arrays, Enum

class GeneratedSetPoints(Parameter):
    """
    A parameter that generates a setpoint array from start, stop, and n_points

                           parameter_class=GeneratedSetPoints,
                           startparam=self.f_start,
                           stopparam=self.f_stop,
                           xpointsparam=self.n_points,
    """
    def __init__(self, startparam, stopparam, xpointsparam, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._startparam = startparam
        self._stopparam = stopparam
        self._xpointsparam = xpointsparam

    def get_raw(self):
        start = self._startparam()
        stop = self._stopparam()
        npts = self._xpointsparam()
        return np.linspace( start, stop, npts )

class SpectrumArray(ParameterWithSetpoints):
    
    def get_raw(self):
       
        dut = self.root_instrument.dut
        RBW = self.root_instrument.RBW()
        average = self.root_instrument.average()
        decimation = self.root_instrument._decimation
        npoints = self.root_instrument.n_points()

       # fstart, fstop, spectra = capture_spectrum( dut,RBW,average,decimation)

     #   flist = np.linspace(fstart,fstop,len(spectra))
      #  __, filteredSpectra = self.root_instrument.filter_span(flist,spectra)


        return self.root_instrument._spectra


class R550_wrapper(Instrument):
    ## wrapper around the pyRF API to use R550 with QCoDes
    def __init__(self,
                 name: str,
                 address: str,
                 **kwargs: Any) -> None:
        super().__init__(name, **kwargs)
        
        self.dut = WSA()
        self.dut.connect(address)
        self.dut.reset()
        self.dut.request_read_perm()


        self._span = 5e6

        self._RBW = 125e6/(32*512)
        self._average = 1
        self._decimation = 1

        self._freqlist = []
        self._spectralist = []
        
        
        self.add_parameter('rfe_mode',
                                unit = '',
                                initial_value= 'SH',
                                label = 'Input Mode',
                                get_cmd = self.dut.rfe_mode,
                                set_cmd = self.dut.rfe_mode,
                                get_parser = str)
        
        self.add_parameter('attenuation',
                                unit = 'dB',
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
                                get_cmd = self.get_avg,
                                set_cmd = self.set_avg,
                                get_parser = int)

        self.add_parameter('ppb',
                                unit = '',
                                #initial_value = 1,
                                label = 'packets/block',
                                get_cmd = self.dut.ppb,
                                set_cmd = self.dut.ppb,
                                get_parser = int,)

        self.add_parameter('spp',
                                unit = '',
                                #initial_value = 32 * 512,
                                label = 'samples/packet',
                                get_cmd = self.dut.spp,
                                set_cmd = self.dut.spp,
                                get_parser = int,)

        self.add_parameter('span',
                                unit = 'Hz',
                                label = 'span',
                                # vals = Numbers(0,100e6),
                                get_cmd = self.get_span,
                                set_cmd = self.set_span ,
                                get_parser = float)

        self.add_parameter('RBW',
                                unit = 'Hz',
                               # initial_value= 125e6 / (self.spp() * self.ppb),
                                label = 'resolution bancwidth',
                                # vals = Numbers(0,100e6),
                                get_cmd = self.get_RBW,
                                set_cmd = self.set_RBW ,
                                get_parser = float)

        self.add_parameter('f_center',
                                unit = 'Hz',
                                label = 'f center',
                                vals = Numbers(0.1e9,27e9),
                                get_cmd = self.dut.freq,
                                set_cmd = self.dut.freq,
                                get_parser = float)

        self.add_parameter('f_start',
                              #  initial_value= 5.1e9,
                                unit='Hz',
                                label='f start',
                                #vals=Numbers(0,1e3),
                                get_cmd= lambda: self.f_center() - self.span()/2,
                                set_cmd= '',
                                get_parser = float)

        self.add_parameter('f_stop',
                                unit='Hz',
                                label='f stop',
                                #initial_value=fstop,
                                #vals=Numbers(1,1e3),
                                get_cmd = lambda: self.f_center() + self.span()/2,
                                set_cmd= '',
                                get_parser = float)

        self.add_parameter('n_points',
                                unit='',
                                # initial_value=len(spectra_data),
                                #vals=Numbers(1,1e3),
                                get_cmd= self.get_npoints,
                                set_cmd= '',
                                get_parser = int)
        
        self.add_parameter('freq_axis',
                                unit='Hz',
                                label='Freq',
                                parameter_class=GeneratedSetPoints,
                                startparam=self.f_start,
                                stopparam=self.f_stop,
                                xpointsparam=self.n_points,
                                vals=Arrays(shape=(self.n_points.get_latest,)))

        self.add_parameter('spectrum',
                                unit='dBm',
                                setpoints=(self.freq_axis,),
                                label='Noise power',
                                parameter_class=SpectrumArray,
                                dut = self.dut,
                                RBW = self.RBW,
                                average = self.average,
                                decimation = self._decimation,
                                vals=Arrays(shape=(self.n_points.get_latest,)))

    ## helper functions
    def filter_span(self,fullFreq,fullSpectra):
            
            freqfilter = (  self.f_start() <  fullFreq ) & ( fullFreq < self.f_stop() )
            spectra = fullSpectra[freqfilter]
            freq = fullFreq[freqfilter]

            self._freqlist = freq
            self._spectra = spectra

            return freq,spectra
    
    ## setters and getters (maybe there's a way of avoiding these?)
    def get_npoints(self):
            
            fstart, fstop, spectra = capture_spectrum(self.dut,self.RBW(),self.average())

            flist = np.linspace(fstart,fstop,len(spectra))

            filteredFreq,filteredSpectra = self.filter_span(flist,spectra)
            
            return len(filteredSpectra)

#     def set_npoints(self,n):
#             self._RBW = 0.81 * self._span()/n ## approximate correction to compensate for usable bins calculation

    def get_avg(self):
            return self._average

    def set_avg(self, avg):
            self._average = avg

    def get_span(self):
            return self._span

    def set_span(self, bw):
            self._span = bw

    def get_RBW(self):
            return self._RBW

    def set_RBW(self, rbw):
            self._RBW = rbw