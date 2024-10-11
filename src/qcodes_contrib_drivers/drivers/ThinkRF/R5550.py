#%%
import numpy as np
from qcodes import Instrument, ParameterWithSetpoints
from qcodes.utils.validators import Arrays, Enum
from pyrf.devices.thinkrf import WSA as _WSA
from pyrf.sweep_device import SweepDevice
from pyrf.numpy_util import calculate_channel_power
from pyrf.connectors.base import sync_async

class WSA(_WSA) :
    """ WSA with bug fix on scpiget/psfm_gain
    """

    def scpiget(self, query:str, timeout=8) -> str:
        """ scpi query, handle bitstring and trailing carriage return
        Args:
            query: scpi-compatible query 
            timeout:  the wait time (in seconds) for response, passed on to super()
        Returns:
            result
        """
        result = super().scpiget(query, timeout)
        return result.rstrip()
    
    def psfm_gain(self, gain=None):
        """
        This command sets or queries one of the Pre-Select Filter Modules's (PSFM) gain stages.

        :param str gain: sets the gain value to 'high', 'medium', 'low', or *None* to query
        :returns: the RF gain value if *None* is used

        Usage:
            dut.psfm_gain('HIGH')
        """
        if self.properties.HAS_PSFM_GAIN:
            GAIN_STATE = {('1', '1'): 'high',
                          ('1', '0'): 'medium',
                          ('0', '0'): 'low'}
            GAIN_SET = {v: k for k, v in list(GAIN_STATE.items())}

            if gain is None:
                gain1 = self.scpiget(":INP:GAIN? 1").decode()
                gain2 = self.scpiget(":INP:GAIN? 2").decode()
                gain = GAIN_STATE[(gain1[0], gain2[0])]
            else:
                state = GAIN_SET[gain.lower()]
                self.scpiset(f":INPUT:GAIN 1 {state[0]}\n")
                self.scpiset(f":INPUT:GAIN 2 {state[1]}\n")

        return gain

class R5550(Instrument):
    """ R5550 insturment class. Wraps the capture_power_spectrum method provided by thinkrf
    """
    def __init__(self, name, address, start=1e6, stop=10e9, averages=1, rfe='SH', rbw=400e3, 
                attenuator=0, gain='low' ):
        """
        Create R5550
        Args:
            name: qcodes paramter name
            address: ip address
            start: start frequency in Hz
            stop: stop frequency in Hz
            averages: number of averages
            rfe: one of SH, SHN, ..
            rbw: resolution bandwidth in Hz
            attenuator: attenuator setting in dB
            gain: gain block value
        """

        super().__init__(name=name)
        self.address = address

        self.connect()
        self._navg = averages
        self.add_parameter('averages', 
                           label='Averages', 
                           unit='#', 
                           get_cmd = lambda : getattr(self, '_navg'),
                           set_cmd = lambda  n : setattr(self, '_navg', n))

        self._rbw=rbw               
        self.add_parameter('rbw', 
                           label='RBW', 
                           unit='Hz', 
                           get_cmd = lambda : getattr(self, '_rbw'),
                           set_cmd = lambda  n : setattr(self, '_rbw', n))

        self._start=start
        self.add_parameter('start', 
                           label='starting frequency', 
                           unit='Hz', 
                           get_cmd = lambda : getattr(self, '_start'),
                           set_cmd = lambda  n : setattr(self, '_start', n))

        self._stop=stop
        self.add_parameter('stop', 
                           label='stopping frequency', 
                           unit='Hz', 
                           get_cmd = lambda : getattr(self, '_stop'),
                           set_cmd = lambda  n : setattr(self, '_stop', n))

        self._rfe=rfe
        self.add_parameter('rfe', 
                           label='RFE Mode', 
                           unit='mode', 
                           get_cmd = lambda : getattr(self, '_rfe'),
                           set_cmd = lambda  n : setattr(self, '_rfe', n))
        
        self._attenuator=attenuator
        self.add_parameter('attenuator', 
                           label='Attenuator', 
                           unit='dB', 
                           get_cmd = lambda : getattr(self, '_attenuator'),
                           set_cmd = lambda  n : setattr(self, '_attenuator', n))
        
        self.add_parameter('channel_power', 
                           label='Channel Power', 
                           unit='dBm', 
                           get_cmd = self.get_channel_pwr)

        self.refresh_faxis()

        self.add_parameter('points',
                           unit='#',
                           label='Points',
                           get_cmd=lambda : self._freq.size )
        
        self.add_parameter('freq_axis',
                           unit='Hz',
                           label='$f$',
                           get_cmd=lambda : self._freq,
                           vals=Arrays(shape=(self.points,)))
        
        # self._gain=00
        self.add_parameter('gain',
                           unit='level',
                           label='gain block',
                           get_cmd = self.dut.psfm_gain,
                           set_cmd = self.dut.psfm_gain,
                           initial_value=gain,
                           vals=Enum('low', 'medium', 'high')
                           )

        self.add_parameter('spectrum',
                   unit='dBm',
                   setpoints=(self.freq_axis,),
                   label='Noise power',
                   parameter_class=ParameterWithSetpoints,
                   get_cmd=self._get_spectrum,
                   vals=Arrays(shape=(self.points,)))

    def capture(self) :
        """ run a capture
        Returns:
            fstart, fstop, spectrum
        """
        sd = self.sd
        device_settings = dict(rfe_mode=self.rfe(), attenuator=self.attenuator())
        cap = sd.capture_power_spectrum(self.start(), self.stop(),
            self.rbw(), device_settings=device_settings,
            mode = self.rfe(), continuous=False)
        return cap
    
    def connect(self) :
        """ connect to WSA
        """
        dut = WSA()
        dut.connect(self.address)
        dut.request_read_perm()
        dut.configure_flattening(loaded=None)
        self.dut = dut
        self.sd = SweepDevice(dut)

    def refresh_faxis(self) :
        """ refresh internal frequency axis. should be called after changing start/stop range
        """
        fstart, fstop, spectral_data = self.capture()
        self._freq = np.linspace(fstart,fstop,len(spectral_data))
    
    def _get_spectrum(self):
        """ get an averaged spectrum
        """
        navg = self.averages()

        spectra_sum = np.zeros(self._freq.size)
        for _ in range(navg) :
            _, _, spectrum = self.capture()
            spectra_sum += spectrum
        return spectra_sum / navg
    
    def get_channel_pwr(self):
        """ calculate channel power from averaged spectrum
        """
        return calculate_channel_power(self.spectrum())

if __name__ == "__main__" :
    spec = R5550(name='r5550', address='169.254.16.253')
