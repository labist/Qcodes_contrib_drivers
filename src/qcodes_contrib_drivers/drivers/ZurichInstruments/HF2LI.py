from typing import Dict, List, Optional, Sequence, Any, Union
from functools import partial
import numpy as np
import logging

from py import process
log = logging.getLogger(__name__)

import time
import matplotlib.pyplot as plt
import numpy as np

import zhinst.utils
import qcodes as qc
from qcodes.instrument.base import Instrument
from qcodes.instrument import InstrumentChannel
import qcodes.utils.validators as vals

from qcodes.instrument.parameter import ParameterWithSetpoints, Parameter

from qcodes.dataset.measurements import Measurement, res_type, DataSaver
from qcodes.instrument.specialized_parameters import ElapsedTimeParameter

class HF2LIDemod(InstrumentChannel):
    """
    HF2LI demod
    """
    def __init__(self, parent: Instrument, name: str, demod : str) -> None:
        """
        Args:
            parent: The Instrument instance to which the channel is
                to be attached (HF2LI).
            name: The 'colloquial' name of the channel
            demod: name for ZI to look up
        """

        super().__init__(parent, name)
        self.demod = demod
        self.dev_id = self.parent.dev_id
        self.daq = self.parent.daq
        # self.clockbase = float(self.daq.getInt(f'/{self.dev_id}/clockbase'))

        # self.model = self._parent.model
        
        if int(demod) in range(6): # x, y, theta only for first 6 demods 
            single_values = (('x', 'Demodulated x', 'V'),
                        ('y', 'Demodulated y', 'V') )
            
            
            for name, unit, label in single_values :
                self.add_parameter( f'{name}',
                        unit=unit,
                        label=label,
                        get_cmd = partial( self._single_get, name )
                )

            self.add_parameter(
                    name=f'theta',
                    label=f'Demodulated theta'+ str(self.demod),
                    unit='deg',
                    get_cmd= self._get_theta,
                    get_parser=float
                )
            
            self.add_parameter(
                name='phase',
                label='Phase',
                unit='deg',
                get_cmd=self._get_phase,
                get_parser=float,
                set_cmd=self._set_phase,
                vals=vals.Numbers(-180,180)
            )

            demod_params = ( 
            ('timeconstant', 's'),
            ('order', ''),
            ('rate', '')
            )
            for param, unit in demod_params :
                self.add_parameter(
                        name=param,
                        label=param,
                        unit=unit,
                        get_cmd= partial( self._get_demod_param, param ),
                        set_cmd= partial( self._set_demod_param, param ),
                        get_parser=float
                    )
            # daq sweeper parameters    
            sweeper = self.daq.sweep()
            sweeper.set("device", self.dev_id)
            sweeper.set("gridnode", f"oscs/{self.parent.sigout}/freq") ### Set the sweeping parameter
            self.sweeper = sweeper

            sweeper_params = ( ( 'samplecount', '', 'Points' ),
                ( 'start', 'Hz', 'Start frequency' ),
                ('stop', 'Hz', 'Stop frequency' ),
                ('xmapping', '', 'X scale as log or linear'),
                ('bandwidthoverlap', '', 'Bandwidth Overlap') )

            for namex, unit, label in sweeper_params :
                self.add_parameter( f'sweeper_{namex}',
                        unit=unit,
                        label=label,
                        set_cmd = partial( self.sweeper.set, namex ),
                        get_cmd = partial( self._sweeper_get, namex )
                )

            self.add_parameter( 'trace_frequency',
                unit='Hz',
                label= 'Frequency',
                snapshot_value=False,
                get_cmd= lambda : self.samples['grid'],
                vals=vals.Arrays(shape=(self.sweeper_samplecount,))
            )
            
            for p, units in ( ('r', 'dB'), ('x','$V_o/V_i$'), ('y','$V_o/V_i$'),('phase', 'deg') ) :
                self.add_parameter( f'trace_{p}',
                        unit= units,
                        label= p,
                        parameter_class = ParameterWithSetpoints,
                        setpoints = ( self.trace_frequency,),
                        get_cmd= partial(self._get_sweep_param, p ),
                        vals=vals.Arrays(shape=(self.sweeper_samplecount,))
                    )
            
            # DAQ spectrum parameters
            daq_module = self.daq.dataAcquisitionModule()
            daq_module.set('device', self.dev_id)
            self.daq_module = daq_module

            self.add_parameter( 'spectrum_samplecount',
                unit='',
                label='number of points',
                set_cmd = partial(self.daq_module.set, 'grid/cols'),
                get_cmd = partial(self._daq_module_get, 'grid/cols')
            )

            self.add_parameter( 'spectrum_repetitions',
                unit='',
                label='number of spectra to acquire',
                initial_value = 1,
                set_cmd = partial(self.daq_module.set, 'grid/repetitions'),
                get_cmd = partial(self._daq_module_get, 'grid/repetitions')
            )

            self.add_parameter( 'spectrum_span',
                unit='Hz',
                label='spectrum frequency span',
                set_cmd=partial(self.daq_module.set, 'spectrum/frequencyspan'),
                get_cmd=partial(self._daq_module_get, 'spectrum/frequencyspan'))
            
            self.add_parameter('spectrum_duration',
                unit='s',
                label='spectrum duration',
                set_cmd= partial(self.daq_module.set, 'duration'),
                get_cmd=partial(self._daq_module_get, 'duration')
            )

            self.add_parameter( 'spectrum_frequency',
                unit='Hz',
                label= 'Frequency',
                snapshot_value=False,
                get_cmd= self._get_spectrum_frequency,
                vals=vals.Arrays(shape=(self._spectrum_freq_length,))
            )

            self.add_parameter( 'spectrum_power',
                unit='$\mathrm{V}^2$/Hz',
                label='Power spectral density',
                parameter_class = ParameterWithSetpoints,
                setpoints = (self.spectrum_frequency,),
                get_cmd = self._get_spectrum_power,
                vals=vals.Arrays(shape=(self._spectrum_freq_length,)))


            self.auto_trigger = False
        
        self.add_parameter(
            name = 'osc',
            label = 'Oscillator',
            get_cmd = self._get_osc,
            get_parser = int,
            set_cmd = self._set_osc,
            vals = vals.Numbers(0,1)
        )

        self.add_parameter(
            name = 'sigout',
            label = 'Sigout Index',
            get_cmd = self._get_sigout,
            vals = vals.Numbers(0,1),
            docstring = """\
            Output signal.
            0: output signal 1
            1: output signal 2
            """
        )

        self.add_parameter(
            name = 'sigin',
            label = 'Sigin Index',
            get_cmd = self._get_sigin, 
            set_cmd = self._set_sigin,
            vals = vals.Numbers(0, 1),
            docstring = """\
            Input signal.
            0: input signal 1
            1: input signal 2
            """
        )

        self.add_parameter(
            name = 'frequency',
            label = 'Frequency',
            unit ='Hz',
            get_cmd = self._get_frequency,
            set_cmd = self._set_frequency,
            get_parser = float
        ) 

        self.add_parameter(
            name = 'sigout_range',
            label = 'Signal output range',
            unit = 'V',
            get_cmd = self._get_sigout_range,
            get_parser = float,
            set_cmd = self._set_sigout_range,
            vals = vals.Enum(0.01, 0.1, 1, 10)
        )

        self.add_parameter(
                name = 'sigout_offset',
                label = 'Signal output offset',
                unit = 'V',
                snapshot_value = True,
                set_cmd = self._set_sigout_offset,
                get_cmd = self._get_sigout_offset,
                vals = vals.Numbers(-10, 10),
                docstring = 'Multiply by sigout_range to get actual offset voltage.'
            )    
        
        self.add_parameter(
                name = 'sigout_amplitude',
                label = 'Signal output mixer amplitude',
                unit = 'Vp',
                get_cmd = partial( self._get_sigout_amplitude ),
                get_parser = float,
                set_cmd = partial( self._set_sigout_amplitude ),
                vals = vals.Numbers(-10, 10),
                docstring = 'Multiply by sigout_range to get actual output voltage.'
            )
        
        self.add_parameter(
                name = 'sigout_enable',
                label = 'On/off for sigout sine wave',
                get_cmd = partial(self._get_sigout_enable),
                set_cmd = partial(self._set_sigout_enable),
                vals=vals.Enum(0,1,2,3),
                docstring="""\
                Sine wave on/off
                0: Channel off (unconditionally)
                1: Channel on (unconditionally)
                2: Channel off (will be turned off on next change of sign from negative to positive)
                3: Channel on (will be turned on on next change of sign from negative to positive)
                """
        )

        self.add_parameter(
                name = 'sigout_on', 
                label = 'on/off for sigout',
                get_cmd = partial(self._get_sigout_on),
                set_cmd = partial(self._set_sigout_on),
                vals = vals.Numbers(0,1),
                docstring="""\
                Output signal on/off.
        
                0: off
                1: on
                """
        )

        self.add_parameter(
            name = 'imp50',
            label = 'on/off for 50 Ohm input impedance',
            get_cmd = partial(self._get_imp50),
            set_cmd = partial(self._set_imp50),
            unit = 'Ohm',
            vals = vals.Enum(0, 1),
            docstring = """\
            Set input impedance
            0: 1 MOhm input impedance
            1: 50 Ohm input impedance
            """
        )

        self.add_parameter(
            name = 'ac_couple',
            label = 'on/off AC coupling for input signal',
            get_cmd = partial(self._get_ac),
            set_cmd = partial(self._set_ac),
            vals = vals.Enum(0, 1),
            docstring = """\
            Coupling for input signals. AC coupling inserts a high-pass filter.
            0: AC coupling off
            1: AC coupling on
            """
        )

        self.add_parameter(
            name = 'diff',
            label = 'on/off for Diff measurements',
            get_cmd = partial(self._get_diff),
            set_cmd = partial(self._set_diff),
            vals = vals.Enum(0, 1),
            docstring = """\
            Toggle between single ended and differential measurements.
            0: Diff off
            1: Diff on
            """
        )

        self.daq.sync()

        self.auto_trigger = False 

    def _get_frequency(self) -> float:
        """
        Get frequency by looking up oscillator 
        """
        osc_index = self.osc()
        path = f'/{self.dev_id}/oscs/{osc_index}/freq/'
        return self.daq.getDouble(path)
    
    def _set_frequency(self, freq) -> float:
        """
        Set frequency by looking up oscillator 
        """
        osc_index = self.osc()
        return self.daq.set([["/%s/oscs/%d/freq" % (self.dev_id, osc_index), freq]])

    def _get_sigin(self):
        """
        Look up index of the input signal
        """
        # LOGIC: check demod number. If 6/7, use
        # daq.setInt('/dev1792/plls/0/adcselect', 0)
        # otherwise stay with what is below
        demod_n = int(self.demod)
        if demod_n in (6,7):
            sigin_index = f'/{self.dev_id}/plls/{demod_n-6}/adcselect/'
        else:
            sigin_index = f'/{self.dev_id}/demods/{self.demod}/adcselect/'
        return self.daq.getInt(sigin_index)
    
    def _set_sigin(self, val: int) -> int:
        """
        Set the index of the input signal
        """
        demod_n = int(self.demod)
        if demod_n not in (6,7):
            raise ValueError('Can only set input for Demod 6,7')
        sigin_index = f'/{self.dev_id}/plls/{demod_n-6}/adcselect/'
        self.daq.setInt(sigin_index, val)
        
    def _get_sigout(self):
        """Look up the index of the output signal"""
        return self.osc()

    def _get_osc(self):
        """Look up the index of oscillator used to demodulate the signal"""
        if self.demod in ['6','7']:
            return int(self.demod) - 6
        else:
            path = f'/{self.dev_id}/demods/{self.demod}/oscselect/'
            return self.daq.getInt(path)
    
    def _set_osc(self, value):
        """Set the index of oscillator used to demodulate the signal"""
        if self.demod in ['6','7']:
            print('Cannot change oscillator for demod 6 or 7')
            return
        else:
            path = f'/{self.dev_id}/demods/{self.demod}/oscselect/'
            self.daq.setInt(path,value)

    def _single_get(self, name):
        """
        get a parameter (used for x and y). only works for demods 0-5.
        """
        path = f'/{self.dev_id}/demods/{self.demod}/sample/'
        return self.daq.getSample(path)[name][0]
    
    def _get_theta(self):
        """
        get theta. only works for demods 0-5. 
        """
        path = f'/{self.dev_id}/demods/{self.demod}/sample/'
        sample = self.daq.getSample(path)
        rad = np.atan2(sample['y'],sample['x'])
        return rad*180/np.pi
    
    def _get_phase(self) -> float:
        """Get the phase shift of the demodulator"""
        path = f'/{self.dev_id}/demods/{self.demod}/phaseshift/'
        return self.daq.getDouble(path)

    def _set_phase(self, phase: float) -> None:
        """Set the phase shift of the demodulator"""
        path = f'/{self.dev_id}/demods/{self.demod}/phaseshift/'
        self.daq.setDouble(path, phase)

    def _get_demod_param( self, param ) :
        """ get demod parameter. used for timeconstant, order, and rate
        Args:
            param: string parameter name. eg timeconstant\
        Returns:
            parameter value as a double

        Example for filter order:
        1: 6 dB/oct slope
        2: 12 dB/oct slope
        3: 18 dB/oct slope
        4: 24 dB/oct slope
        5: 30 dB/oct slope
        6: 36 dB/oct slope
        7: 42 dB/oct slope
        8: 48 dB/oct slope
        """
        path = f'/{self.dev_id}/demods/{self.demod}/{param}/'
        return self.daq.getDouble(path)


    def _set_demod_param( self, param, value ) :
        """ set demod parameter
        Args:
            param: string parameter name. eg timeconstant\
        Returns:
            parameter value as a double
        """
        path = f'/{self.dev_id}/demods/{self.demod}/{param}/'
        self.daq.setDouble(path, value)

    def _sweeper_get( self, name ) :
        """ wrap zi sweeper.get"""
        return self.sweeper.get( name )[name][0]
    
    def _daq_module_get(self, name):
        path = name.split('/')
        param = self.daq_module.get(name)
        for i in path:
            param = param[i]
        return param[0]
    
    def _get_sigout_range(self, sigout=None ) -> float:
        # if sigout is None :
        #     sigout = self.sigout
        path = f'/{self.dev_id}/sigouts/{self.sigout()}/range/'
        return self.daq.getDouble(path)

    def _set_sigout_range(self, rng: float, sigout=None ) -> None:
        if sigout is None :
            sigout = self.sigout       
        path = f'/{self.dev_id}/sigouts/{self.sigout()}/range/'
        self.daq.setDouble(path, rng)

    def _get_sigout_offset(self) -> float:
        path = f'/{self.dev_id}/sigouts/{self.sigout()}/offset/'
        range = self._get_sigout_range()
        return self.daq.getDouble(path)*range

    def _set_sigout_offset(self, offset: float) -> None:
        path = f'/{self.dev_id}/sigouts/{self.sigout()}/offset/'
        range = self._get_sigout_range()
        return self.daq.setDouble(path, offset/range)

    
    def _get_sigout_amplitude(self) -> float:
        mixer_channel = self.sigout() + 6
        path = f'/{self.dev_id}/sigouts/{self.sigout()}/amplitudes/{mixer_channel}/'
        range = self._get_sigout_range(sigout=self.sigout())
        return self.daq.getDouble(path) * range

    def _set_sigout_amplitude(self, amp: float) -> None:
        mixer_channel = self.sigout() + 6
        path = f'/{self.dev_id}/sigouts/{self.sigout()}/amplitudes/{mixer_channel}/'
        range = self._get_sigout_range(sigout=self.sigout())
        return self.daq.setDouble(path, amp/range)

    def _get_sigout_enable(self) -> int:
        mixer_channel = self.sigout() + 6
        path = f'/{self.dev_id}/sigouts/{self.sigout()}/enables/{mixer_channel}/'
        return self.daq.getInt(path)

    def _set_sigout_enable(self, val: int) -> None:
        mixer_channel = self.sigout() + 6
        path = f'/{self.dev_id}/sigouts/{self.sigout()}/enables/{mixer_channel}/'
        self.daq.setInt(path, val)

    def _get_sigout_on(self) -> int:
        path = f'/{self.dev_id}/sigouts/{self.sigout()}/on'
        return self.daq.getInt(path)

    def _set_sigout_on(self, val: int) -> int:
        path = f'/{self.dev_id}/sigouts/{self.sigout()}/on'
        self.daq.setInt(path, val)    
    
    def _get_imp50(self) -> int:
        path = f'/{self.dev_id}/sigins/{self.sigin()}/imp50'
        return self.daq.getInt(path)
    
    def _set_imp50(self, val:int) -> int:
        path = f'/{self.dev_id}/sigins/{self.sigin()}/imp50'
        self.daq.setInt(path, val)

    def _get_ac(self) -> int:
        path = f'/{self.dev_id}/sigins/{self.sigin()}/ac'
        return self.daq.getInt(path)

    def _set_ac(self, val:int) -> int:
        path = f'/{self.dev_id}/sigins/{self.sigin()}/ac'
        self.daq.setInt(path, val)

    def _get_diff(self) -> int:
        path = f'/{self.dev_id}/sigins/{self.sigin()}/diff'
        return self.daq.getInt(path)

    def _set_diff(self, val:int) -> int:
        path = f'/{self.dev_id}/sigins/{self.sigin()}/diff'
        self.daq.setInt(path, val)

    def _get_sweep_param(self, param, fr=True):
        if self.auto_trigger :
            self.trigger_sweep()

        if param == 'phase' :
            values = (self.samples[param])*180/np.pi

        elif param == 'r':
            amplitude = self.sigout_amplitude() / np.sqrt(2) # normalization factor for vpk
            values = 20 * np.log10( self.samples[param] / amplitude )

        else :
            amplitude = self.sigout_amplitude() / np.sqrt(2) # normalization factor for vpk
            values = self.samples[param] / amplitude

        return values
    
    def _get_spectrum_power(self):
        # Divide out the filter transfer function from the (averaged) absolute FFT of the spectrum.
        compensated_samples = self.spectrum_samples['value'][0] / self.spectrum_filter['value'][0]
        # convert compensated FFT to PSD by squaring and normalizing by frequency bin width
        return np.power(compensated_samples, 2) / self.spectrum_samples["header"]["gridcoldelta"][0]
        
    def _spectrum_freq_length(self):
        return len(self.spectrum_samples["timestamp"][0])

    def _get_spectrum_frequency(self):
        bin_count = len(self.spectrum_samples["value"][0])
        bin_resolution = self.spectrum_samples["header"]["gridcoldelta"][0]
        center_freq = self.spectrum_samples['header']['center'][0]
        frequencies = np.arange(bin_count)

        bandwidth = bin_resolution * len(frequencies)
        frequencies = center_freq + (
        frequencies * bin_resolution - bandwidth / 2.0 + bin_resolution / 2.0)
        return frequencies

    def trigger_sweep(self):
        # sweeper = self.daq.sweep()
        #self.snapshot(update=True)
        sweeper = self.sweeper
        sweeper.set("device", self.dev_id)
        sweeper.set('gridnode', f'oscs/{self.osc()}/freq')

        # Params for type of scan:
        # 0: sequential sweep
        # 1: binary sweep
        # 2: bidirectional sweep
        # 3: reverse sweep
        sweeper.set('scan', 0)

        # sweeper.set("bandwidthcontrol", 0) ### Bandwidth control: Auto
        #sweeper.set('maxbandwidth', 100) ### Max demodulation bandwidth
        sweeper.set('settling/inaccuracy', 100e-06)
        path = f"/{self.dev_id}/demods/{self.demod}/sample"
        sweeper.set("start", self.sweeper_start())
        sweeper.set("stop", self.sweeper_stop())
        sweeper.set("xmapping", self.sweeper_xmapping())  # 0 for linear in x, 1 for log in x
        sweeper.set("samplecount", self.sweeper_samplecount()) 
        #sweeper.set()
        sweeper.subscribe(path)
        sweeper.execute()

        ### Wait until measurement is done 
        start_t = time.time()
        timeout = 6000  # [s]
        while not sweeper.finished():  # Wait until the sweep is complete, with timeout.
            time.sleep(1)
            progress = sweeper.progress()
            if (time.time() - start_t) > timeout:
                print("\nSweep still not finished, forcing finish...")
                sweeper.finish()
        data = sweeper.read(True)
        self.samples = data[path][0][0]
        sweeper.unsubscribe(path) ### Unsubscribe from the signal path

    def trigger_spectrum(self, subscribed_paths = ("sample.xiy.fft.abs.filter", "sample.xiy.fft.abs.avg") ):
        """
        Default things to subscribe:
        sample.xiy.fft.abs.filter
        sample.xiy.fft.abs.avg
        """
        daq_module = self.daq_module
        #self.snapshot(update=True)
        daq_module.set('device', self.dev_id)
        daq_module.set("type", 0) # continuous triggering
        daq_module.set("grid/mode", 4) 
        daq_module.set("count", 1) # number of triggers
        daq_module.set("grid/cols", self.spectrum_samplecount())
        daq_module.set('grid/repetitions', self.spectrum_repetitions())
        daq_module.set("spectrum/frequencyspan", self.spectrum_span())
        
        for p in subscribed_paths :
            path = f"/{self.dev_id}/demods/{self.demod}/{p}" # .pwr?
            daq_module.subscribe(path)
            daq_module.set("spectrum/autobandwidth", 1)
            daq_module.set('spectrum/enable', 1)
        daq_module.execute()

        start = time.time()
        timeout = 60000  # [s]

        while not daq_module.finished():
            time.sleep(0.2)
            if (time.time() - start) > timeout:
                print("\ndaqModule still not finished, forcing finish...")
                daq_module.finish()

        data = daq_module.read(True)
        self.spectrum_filter = data[f"/{self.dev_id}/demods/{self.demod}/sample.xiy.fft.abs.filter"][0]
        self.spectrum_samples = data[f"/{self.dev_id}/demods/{self.demod}/sample.xiy.fft.abs.avg"][0]

        for p in subscribed_paths:
            daq_module.unsubscribe(path)

    def _get_data(self, poll_length=0.1) -> float:
        path = f'/{self.dev_id}/demods/{self.demod}/sample'
        self.daq.unsubscribe("*")
        poll_timeout = 500  # [ms]
        poll_flags = 0
        poll_return_flat_dict = True
        self.daq.sync()
        self.daq.subscribe(path)
        data = self.daq.poll(poll_length, poll_timeout, poll_flags, poll_return_flat_dict)
        self.daq.unsubscribe("*")
        return data

    def readout(self, poll_length : Optional[float] = 0.1 ):
        """ record self.demod
        Args:
            poll_length: length of time in seconds to record for
        Returns:
            X, Y, t as np arrays
        """
        path = f'/{self.dev_id}/demods/{self.demod}/sample'
        data = self._get_data( poll_length=poll_length )
        sample = data[path]
        X = sample['x']
        Y = sample['y']
        clockbase = float(self.daq.getInt(f'/{self.dev_id}/clockbase'))
        t = (sample['timestamp'] - sample['timestamp'][0]) / clockbase 
        return (X, Y, t)
    

class HF2LI(Instrument):
    """
    Qcodes driver for Zurich Instruments HF2LI lockin amplifier.

    This driver is meant to emulate a single-channel lockin amplifier,
    so one instance has a single demodulator, a single sigout channel,
    and multiple auxout channels (for X, Y, R, Theta, or an arbitrary manual value).
    Multiple instances can be run simultaneously as independent lockin amplifiers.

    This instrument has a great deal of additional functionality that is
    not currently supported by this driver.

    Args:
        name: Name of instrument.
        device: Device name, e.g. "dev204", used to create zhinst API session.
        demod: Index of the demodulator to use.
        sigout: Index of the sigout channel to use as excitation source.
        # sigin: Index of the sigin channel being used.
        auxouts: Dict of the form {output: index},
            where output is a key of HF2LI.OUTPUT_MAPPING, for example {"X": 0, "Y": 3}
            to use the instrument as a lockin amplifier in X-Y mode with auxout channels 0 and 3.
        sigout2mixer: mapping from sigout to mixers. For default HF2LI {0:6, 1:7}
        num_sigout_mixer_channels: Number of mixer channels to enable on the sigouts. Default: 1.
    """
    # OUTPUT_MAPPING = {-1: 'manual', 0: 'X', 1: 'Y', 2: 'R', 3: 'Theta'}
    # OUTPUT_MAPPING = {1: 'manual', 0: 'X', 3: 'Y'}#, 2: 'R', 3: 'Theta'}
    def __init__(self, name: str, device: str, demod: int, sigout: int,
            auxouts: Dict[str, int], 
            sigout2mixer : Dict[ int, int ]={0:6, 1:7},
            num_sigout_mixer_channels: int=1, 
            **kwargs) -> None:

        super().__init__(name, **kwargs)
        instr = zhinst.utils.create_api_session(device, 1 )#, 
            #required_devtype='HF2LI') #initializes the instrument
        self.daq, self.dev_id, self.props = instr
        self.demod = demod
        self.sigout = sigout
        self.auxouts = auxouts
        log.info(f'Successfully connected to {name}.')
        self.sigout2mixer = sigout2mixer

        for ch in self.auxouts: #NOT MIGRATED
            self.add_parameter( #NOT MIGRATED
                name=f'aux_{ch}',
                label=f'Scaled {ch} output value',
                unit='V',
                get_cmd=lambda channel=ch: self._get_output_value(channel),
                get_parser=float,
                docstring=f'Scaled and demodulated {ch} value.'
            )

            self.add_parameter( #NOT MIGRATED
                name=f'offset_aux_{ch}',
                label=f'{ch} output offset',
                unit='V',
                get_cmd=lambda channel=ch: self._get_offset(channel),
                get_parser=float,
                set_cmd=lambda offset, channel=ch: self._set_offset(offset, channel),
                vals=vals.Numbers(-2560, 2560),
                docstring=f'Manual offset for {ch}, applied after scaling.'
            )
            # self.add_parameter(
            #     name=f'output_{ch}',
            #     label=f'{ch} output select',
            #     get_cmd=lambda channel=ch: self._get_output_select(channel),
            #     get_parser=str
            # )
            # Making output select only gettable, since we are
            # explicitly mapping auxouts to X, Y, R, Theta, etc.
            # self._set_output_select(ch)
            
        self.add_parameter( #NOT MIGRATED
            name='ext_clk',
            label='External Clock',
            unit='',
            set_cmd=self._set_ext_clk,
            get_cmd=self._get_ext_clk,
            vals=vals.Bool()
        )

        demods = [str(i) for i in range(8)]
        for d in demods:
            d_name = f'demod_{d}'
            demod = HF2LIDemod(self, d_name, d)
            self.add_submodule(d_name, demod)


    
    def _set_ext_clk(self, val):
        """ set external 10 MHz clock
        """
        path = f'/{self.dev_id}/system/extclk'
        self.daq.setInt(path, int(val) )

    def _get_ext_clk( self ):
        """ get external 10 MHz clock as bool
        """
        path = f'/{self.dev_id}/system/extclk'
        val = self.daq.getInt( path )
        return bool( val )
     
    def _get_gain(self, channel: str) -> float:
        path = f'/{self.dev_id}/auxouts/{channel}/scale/'
        return self.daq.getDouble(path)

    def _set_gain(self, gain: float, channel: str) -> None:
        path = f'/{self.dev_id}/auxouts/{channel}/scale/'
        self.daq.setDouble(path, gain)

    def _get_offset(self, channel: str) -> float:
        path = f'/{self.dev_id}/auxouts/{channel}/offset/'
        return self.daq.getDouble(path)

    def _set_offset(self, offset: float, channel: str) -> None:
        path = f'/{self.dev_id}/auxouts/{channel}/offset/'
        self.daq.setDouble(path, offset)

    def _get_output_value(self, channel: str) -> float:
        path = f'/{self.dev_id}/auxouts/{channel}/value/'
        return self.daq.getDouble(path)

    # def _get_output_select(self, channel: str) -> str:
    #     path = f'/{self.dev_id}/auxouts/{self.auxouts[channel]}/outputselect/'
    #     idx = self.daq.getInt(path)
    #     return self.OUTPUT_MAPPING[idx]

    # def _set_output_select(self, channel: str) -> None:
    #     path = f'/{self.dev_id}/auxouts/{self.auxouts[channel]}/outputselect/'
    #     keys = list(self.OUTPUT_MAPPING.keys())
    #     idx = keys[list(self.OUTPUT_MAPPING.values()).index(channel)]
    #     self.daq.setInt(path, idx)
        
    def ask(self,arg) :
        """" hacking in an ask method
        """
        if arg == "*IDN?" :
            return self.dev_id
        else :
            raise ValueError(f"I don't understand {arg}")