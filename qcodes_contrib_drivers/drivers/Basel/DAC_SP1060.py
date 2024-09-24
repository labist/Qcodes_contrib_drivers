"""Driver for the Basel LNHR DAC II SP1060

Using Python to control the Basel SP1060 with
parameters to record values simply. Individual
channels, ramp generators, and AWGs are defined
as their own classes to then be iterated within
the SP1060 overall instrument class to create a
heirarchy within the driver. Each class (excluding
SP1060) then has its appropriate commands as
attributes.

dac = SP1060('LNHR', 'TCPIP0::192.168.0.5::23::SOCKET', num_chans=12, voltage_post_delay=0.01)
dac.ch1.status('ON') # turn channel output on
dac.ch1.volt(3) # set a voltage
dac.ramphelper(start=0, stop=1, period=0.3, channel=1, cycles=2) # perform two ramps

"""


import time
import pyvisa as visa
from typing import Sequence, Any
from qcodes import VisaInstrument, InstrumentChannel, ChannelList
from qcodes.instrument.channel import MultiChannelInstrumentParameter
from qcodes.utils import validators as vals
from qcodes.parameters import Parameter

class SP1060Exception(Exception):
    pass


class SP1060Reader(object):
    def _vval_to_dacval(self, vval):
        """
        Convert voltage to DAC value 
        dacval=(Vout+10)*838860.75 
        """
        try:
            dacval = int((float(vval)+10)*838860.75 )
            return dacval
        except:
            pass

    def _dacval_to_vval(self, dacval):
        """
        Convert DAC value to voltage
        Vout=(dacval/838860.75 )–10
        """
        try:
            vval = round((int(dacval.strip(),16)/float(838860.75))-10, 6)
            return vval
        except:
            pass


class SP1060MultiChannel(MultiChannelInstrumentParameter, SP1060Reader):
    def __init__(self, channels:Sequence[InstrumentChannel], param_name: str, *args: Any, **kwargs: Any):
        super().__init__(channels, param_name, *args, **kwargs)
        self._channels = channels
        self._param_name = param_name
        
        def get_raw(self):
            output = tuple(chan.parameters[self._param_name].get() for chan in self._channels)
            return output
        
        def set_raw(self, value):
            for chan in self._channels:
                chan.volt.set(value)
    

class SP1060Channel(InstrumentChannel, SP1060Reader):
    """
    Defining the general characteristics of each channel

    Defines the general commands/aspects of each channel
    as attributes to then define the individual channels
    as part of the overall SP1060 class.

    Attributes:
        volt: Set/Get voltage output
        status: Set/Get the channel being on/off
        registered: Get the registered voltage output (???)
        bw: Set/Get the bandwidth of the channel (low or high)
        mode: Get any errors/settings for the channel
    """
    def __init__(self, parent, name, channel, min_val=-10, max_val=10, 
                 voltage_post_delay=0.02, voltage_step=0.01):
        """Initializes the channel based on a given voltage range

        Args:
            volt: Float number to set/get voltage output
            status: String to set/get the channel being on/off
            registered: Float number to get the registered voltage output (???)
            bw: String to set/get  bandwidth of the channel (low or high)
            mode: String to get any errors/settings for the channel
        """
        super().__init__(parent, name)
        
        # validate channel number
        self._CHANNEL_VAL = vals.Ints(1,24)
        self._CHANNEL_VAL.validate(channel)
        self._channel = channel

        # limit voltage range
        self._volt_val = vals.Numbers(min(min_val, max_val), max(min_val, max_val))
        
        """clarify difference with registered"""
        self.volt: Parameter = self.add_parameter('volt',
                           label = 'C {}'.format(channel),
                           unit = 'V',
                           set_cmd = self._set_voltage,
                           set_parser = self._vval_to_dacval,
                           post_delay = voltage_post_delay,
                           step = voltage_step,
                           get_cmd = self._read_voltage,
                           vals = self._volt_val 
                           )

        self.status: Parameter = self.add_parameter('status',
                            label = f'chan{channel} status',
                            set_cmd = f"{channel} {{}}",
                            get_cmd = f'{channel} S?',
                            vals = vals.Enum('ON', 'OFF')
                            )
        
        """clarify difference with volt"""
        self.rg: Parameter = self.add_parameter('registered',
                            label = f'chan{channel} registered',
                            unit = 'V', 
                            get_cmd = f'{channel} VR?',
                            get_parser = self._dacval_to_vval,
                            vals = self._volt_val
                            )

        self.bw: Parameter = self.add_parameter('bw',
                            label = f'chan{channel} bw',
                            set_cmd = f"{channel} {{}}",
                            get_cmd = f'{channel} BW?',
                            vals = vals.Enum('LBW', 'HBW')
                            )

        self.mode: Parameter = self.add_parameter('mode',
                            label = f'chan{channel} mode',
                            get_cmd = f'{channel} M?',
                            vals = vals.Enum('ERR', 'DAC', 'SYN', 'RMP', 'AWG', '---')
                            )

    def _set_voltage(self, code):
        """ set the voltage. always query it first to make sure qcodes' internal value is correct
        """
        chan = self._channel
        return self.parent.write('{:0} {:X}'.format(chan, code))
            
    def _read_voltage(self):
        chan = self._channel
        dac_code=self.parent.write('{:0} V?'.format(chan))
        return self._dacval_to_vval(dac_code)


class RampGenerator(InstrumentChannel, SP1060Reader):
    """Defines class of Ramp generators
    
    Defines the general commands/aspects of the
    ramp generators to be called later once
    individual ones are specified within the
    SP1060 class

     Attributes:
        control: String to start, stop, hold a ramp gen
        state: String to get the ramp gen being idle, ramping
            up, ramping down, or holding. When ramp gen is
            stopped manually or finishes its cycles, it will
            hold the stopping voltage until the channel is
            manually set to another voltage or until the
            channel is affected by another generator (this
            is a quality of the dac itself)
        ava: Boolean to get if selected channel is not under
            use by another ramp gen/AWG
        selchan: Integer to set/get the ramp gen's output channel        
        start: Float to set/get the starting voltage        
        stop: Float to set/get the ending voltage
        period: Float to set/get the time to complete one cycle (sec)
        shape: String to set/get either a sawtooth or triangle cycle
        cycles: Integer to set/get the cycles to run (if 0 selected,
            will run infinitely until told to stop manually)
        mode: String to set/get the ramp gen being in ramp or step
            mode (step is used for 2D-Scans)
        cycles_done: Integer to get the cycles completed by the
            ramp gen. Retains value after full cycles completed
        steps_done: Integer to get the steps completed by the ramp
            gen. Does not retain value after a cycle is completed
        step: Float to get the resolution of the slope (internally
            calculated via period, start/stop, and shape)
        spc: Integer value to get the internally calculated steps
            per cycle
    """
    
    def __init__(self, parent, name, generator, min_val=-10, max_val=10, num_chans = 24):
        """Initializes the ramp gen by a given voltage range and possible channels
        
        Args:
            control: String to start, stop, hold a ramp gen
            state: String to get the ramp gen being idle, ramping
            up, ramping down, or holding. When ramp gen is
            stopped manually or finishes its cycles, it will
            hold the stopping voltage until the channel is
            manually set to another voltage or until the
            channel is affected by another generator (this
            is a quality of the dac itself)
            ava: Boolean to get if selected channel is not under
                use by another ramp gen/AWG
            selchan: Integer to set/get the ramp gen's output channel        
            start: Float to set/get the starting voltage        
            stop: Float to set/get the ending voltage
            period: Float to set/get the time to complete one cycle (sec)
            shape: String to set/get either a sawtooth or triangle cycle
            cycles: Integer to set/get the cycles to run (if 0 selected,
                will run infinitely until told to stop manually)
            mode: String to set/get the ramp gen being in ramp or step
                mode (step is used for 2D-Scans)
            cycles_done: Integer to get the cycles completed by the
                ramp gen. Retains value after full cycles completed
            steps_done: Integer to get the steps completed by the ramp
                gen. Does not retain value after a cycle is completed
            step: Float to get the resolution of the slope (internally
                calculated via period, start/stop, and shape)
            spc: Integer value to get the internally calculated steps
               per cycle
        """
        super().__init__(parent, name)

        # first allow the numbering of the generators
        self._GENERATOR_VAL = vals.Enum('a', 'b', 'c', 'd')
        self._GENERATOR_VAL.validate(generator)
        self._generator = generator

        # limit voltage range
        self._volt_val = vals.Numbers(min(min_val, max_val), max(min_val, max_val))

        #then list all of their attributes
        self.control: Parameter = self.add_parameter('control',
                                label = f'{name} control',
                                set_cmd = self._set_control,
                                vals = vals.Enum('START', 'HOLD', 'STOP')
                                )
        
        self.state: Parameter = self.add_parameter('state',
                                label = f'{name} state',
                                get_cmd = f'C RMP-{generator} S?',
                                get_parser = self._state_get_parser
                                )
        
        self.ava: Parameter = self.add_parameter('ava',
                                label = f'{name} ava',
                                get_cmd = f'C RMP-{generator} AVA?',
                                get_parser = bool,
                                vals = vals.Bool()
                                )
        
        self.selchan: Parameter = self.add_parameter('selchan',
                                label = f'{name} selchan',
                                set_cmd = f"C RMP-{generator} CH {{}}",
                                get_cmd = f'C RMP-{generator} CH?',
                                get_parser = int,
                                vals = vals.Numbers(min(1, num_chans), max(1, num_chans))
                                )
        
        self.start: Parameter = self.add_parameter('start',
                                label = f'{name} start',
                                unit = 'V',
                                set_cmd = f"C RMP-{generator} STAV {{}}",
                                get_cmd = f'C RMP-{generator} STAV?',
                                get_parser = float,
                                vals = self._volt_val
                                )
        
        self.stop: Parameter = self.add_parameter('stop',
                                label = f'{name} stop',
                                unit = 'V',
                                set_cmd = f"C RMP-{generator} STOV {{}}",
                                get_cmd = f'C RMP-{generator} STOV?',
                                get_parser = float,
                                vals = self._volt_val
                                )

        self.period: Parameter = self.add_parameter('period',
                                label = f'{name} period',
                                unit = 's',
                                set_cmd = f"C RMP-{generator} RT {{}}",
                                get_cmd = f'C RMP-{generator} RT?',
                                get_parser = float,
                                vals = vals.Numbers(0.05, 1000000)
                                )

        self.shape: Parameter = self.add_parameter('shape',
                                label = f'{name} shape',
                                set_cmd = f"C RMP-{generator} RS {{}}",
                                get_cmd = f'C RMP-{generator} RS?',
                                set_parser = self._shape_set_parser,
                                get_parser = self._shape_get_parser,
                                vals = vals.Enum('sawtooth', 'triangle')
                                )
        
        self.cycles: Parameter = self.add_parameter('cycles',
                                label = f'{name} cycles',
                                set_cmd = f"C RMP-{generator} CS {{}}",
                                get_cmd = f'C RMP-{generator} CS?',
                                get_parser = int,
                                vals = vals.Ints(0, 4000000000)
                                )
        
        self.mode: Parameter = self.add_parameter('mode',
                                label = f'{name} mode',
                                set_cmd = f"C RMP-{generator} STEP {{}}",
                                get_cmd = f'C RMP-{generator} STEP?',
                                set_parser = self._mode_set_parser,
                                get_parser = self._mode_get_parser,
                                vals = vals.Enum('ramp', 'step')
                                )
        
        self.cycles_done: Parameter = self.add_parameter('cycles_done',
                                label = f'{name} cycles_done',
                                get_cmd = f'C RMP-{generator} CD?',
                                get_parser = int,
                                vals = vals.Ints(0, 4000000000)
                                )
        
        self.steps_done: Parameter = self.add_parameter('steps_done',
                                label = f'{name} steps_done',
                                get_cmd = f'C RMP-{generator} SD?',
                                get_parser = int,
                                vals = vals.Ints(0, 4000000000)
                                )
        
        self.step: Parameter = self.add_parameter('step',
                                label = f'{name} step',
                                unit = 'V',
                                get_cmd = f'C RMP-{generator} SSV?',
                                get_parser = float,
                                vals = self._volt_val
                                )
        
        self.spc: Parameter = self.add_parameter('spc',
                                label = f'{name} spc',
                                get_cmd = f'C RMP-{generator} ST?',
                                get_parser = int,
                                vals = vals.Ints(10, 200000000)
                                )
    
    def _set_control(self, val):
        """
        Set the control state of a ramp generator.
        Prints a warning message if the selected
        channel is not on and thus not outputting
        the voltage. Also clears the cache to force
        previous channel voltages to be forgotten
        so when cycles are finished/halted the
        channel uses this ending voltage as its
        next starting point rather than the
        previously set channel voltage causing a
        jump in voltage level
        Args:
            val: START/STOP/HOLD
        """
        chan_num = self.selchan()
        channel = self.parent.channels[chan_num-1]

        if val == 'START': # clear cache to avoid jumps if user sets channel voltage
            channel.volt.cache._update_with(value=None, raw_value=None)
        if channel.status() == 'OFF':
            print(f'Warning: {chan_num} not on, ramping anyway') # print a warning if channel is not on
        self.write(f"C RMP-{self._generator} {val}")
        
    def _state_get_parser(self, stateval):
        """
        Parser to get the current state of the ramp generator
        Args:
            val: idle, ramping up, ramping down, holding voltage
        """
        naraco = {'0':' idle', '1':'rampup', '2':'rampdown', '3':'holding'}
        return naraco[stateval]
    
    def _shape_set_parser(self, shapeval):
        """
        Parser to sets the shape of the ramp
        generator to complete in a single period
        Args:
            val: sawtooth, triangle
        """
        dict = {'sawtooth':0, 'triangle':1}
        return dict[shapeval]
    
    def _shape_get_parser(self, shapeval):
        """
        Parser to get the shape of the ramp
        generator to complete in a single period
        Args:
            val: sawtooth, triangle
        """
        cammie = {'0':'sawtooth', '1':'triangle'}
        return cammie[shapeval]

    def _mode_set_parser(self, modeval):
        """
        Parser to set the ramp to either be
        in ramp mode (normal ramp) or step
        mode (used only for 2D-Scans)
        Args:
            val: ramp, step
        """
        dict = {'ramp':0, 'step':1}
        return dict[modeval]
    
    def _mode_get_parser(self, modeval):
        """
        Parser to get the ramp either in
        ramp mode (normal ramping) or step
        mode (only for 2D-Scans)
        Args:
            val: ramp, step
        """
        xof = {'0':'ramp', '1':'step'}
        return xof[modeval]


class AWG(InstrumentChannel, SP1060Reader):
    """Defines the class of AWGs

    Defines the general commands/aspects of the
    AWGs to be called later once the individual
    ones are defined within the SP1060 class

    Attributes:
        block: String to set AWGs to either run independently
            or stop all other non-AWG channels' activity
        control: String to start/stop the AWG
        state: String to get whether AWG is idling or running
        cycles_done: Integer to get the cycles completed by the AWG
        cycle_period: Float to get the duration of one AWG cycle
        ava: String to get whether the selected channel is
            available for the AWG to run (false if channel is
            in use by another AWG)
        selchan: Integer to set/get the AWG/s output channel
        memsize: Integer to set/get the AWG memory size
        cycles: Integer to set/get AWG cycles to run
        ??? EXTERNAL TRIGGER ???
        clock: Integer to set/get the AWG clock period for
            the upper or lower board
        mhzclock: String to set/get the 1MHz Clock to be on
            or off. Can be used internally for the AWGs or
            to sync up the entire DAC with external devices
    """
    def __init__(self, parent, name, arbitrary_generator, num_chans = 24):
        """
        Initializes the AWG given the 12/24 possible channels

        Args:
            block: String to set AWGs to either run independently
                or stop all other non-AWG channels' activity
            control: String to start/stop the AWG
            state: String to get whether AWG is idling or running
            cycles_done: Integer to get the cycles completed by the AWG
            cycle_period: Float to get the duration of one AWG cycle
            ava: String to get whether the selected channel is
                available for the AWG to run (false if channel is
                in use by another AWG)
            selchan: Integer to set/get the AWG/s output channel
            memsize: Integer to set/get the AWG memory size
            cycles: Integer to set/get AWG cycles to run
            ??? EXTERNAL TRIGGER ???
            clock: Integer to set/get the AWG clock period for
                the upper or lower board(s)
            mhzclock: String to set/get the 1MHz Clock to be on
            or off. Can be used internally for the AWGs or
            to sync up the entire DAC with external devices
        """
        super().__init__(parent, name)

        # first allow the numbering of the generators
        self._GENERATOR_VAL = vals.Enum('a', 'b', 'c', 'd')
        self._GENERATOR_VAL.validate(arbitrary_generator)
        self._arbitrary_generator = arbitrary_generator

        #now add some attributes
        ##### AWG functionality
        self.block: Parameter = self.add_parameter('block',
                                label = f'{name} block',
                                set_cmd = self._block_set,
                                get_cmd = self._block_get,
                                get_parser = self._block_get_parser
                                )

        self.control: Parameter = self.add_parameter('control',
                                label = f'{name} control',
                                set_cmd = self._set_control,
                                #vals = vals.Enum('START', 'STOP')
                                )
        
        self.state: Parameter = self.add_parameter('state',
                                label = f'{name} state',
                                get_cmd = f'C AWG-{arbitrary_generator} S?',
                                get_parser = self._state_get_parser
                                )
        
        self.cycles_done: Parameter = self.add_parameter('cycles_done',
                                label = f'{name} cycles_done',
                                get_cmd = f'C AWG-{arbitrary_generator} CD?',
                                get_parser = int,
                                vals = vals.Ints(0, 4000000000)
                                )
        
        self.cycle_period: Parameter = self.add_parameter('cycle_period',
                                label = f'{name} cycle_period',
                                unit = 's',
                                get_cmd = f'C AWG-{arbitrary_generator} DP?',
                                get_parser = float,
                                vals = vals.Enum(20e-6, 1.36e8)
                                )
        
        self.ava: Parameter = self.add_parameter('ava',
                                label = f'{name} ava',
                                get_cmd = f'C AWG-{arbitrary_generator} AVA?',
                                get_parser = self._ava_get_parser
                                )
        
        self.selchan: Parameter = self.add_parameter('selchan',
                                label = f'{name} selchan',
                                set_cmd = f'C AWG-{arbitrary_generator} CH {{}}',
                                get_cmd = f'C AWG-{arbitrary_generator} CH?',
                                get_parser = int,
                                vals = vals.Ints(1, num_chans)
                                #FIX SO ONLY A,B CAN ACCESS 1-12, ETC
                                )

        self.memsize: Parameter = self.add_parameter('memsize',
                                label = f'{name} memsize',
                                set_cmd = f'C AWG-{arbitrary_generator} MS {{}}',
                                get_cmd = f'C AWG-{arbitrary_generator} MS?',
                                get_parser = int,
                                vals = vals.Ints(2,34000)
                                )
        
        self.cycles: Parameter = self.add_parameter('cycles',
                                label = f'{name} cycles',
                                set_cmd = f'C AWG-{arbitrary_generator} CS {{}}',
                                get_cmd = f'C AWG-{arbitrary_generator} CS?',
                                get_parser = int,
                                vals = vals.Numbers(0, 4e9)
                                )
        
        ##AWG External Trigger Mode

        self.clock: Parameter = self.add_parameter('clock',
                                label = f'{name} clock',
                                unit = 'microseconds',
                                set_cmd = self._clock_set,
                                get_cmd = self._clock_get,
                                get_parser = int,
                                vals = vals.Numbers(10,4e9)
                                )

        self.mhzclock: Parameter = self.add_parameter('mhzclock',
                                label = f'{name} mhzclock',
                                set_cmd = f'C AWG-1MHz {{}}',
                                get_cmd = f'C AWG-1MHz?',
                                set_parser = self._mhz_set_parser,
                                get_parser = self._mhz_get_parser,
                                )
    
    # Function Commands    
    def _block_set(self, input):
        """
        Command to set whether when an AWG runs
        it blocks all non-AWG behavior through
        the channels on its respective board

        Args:
            board: Which board to be altered, AB
                (lower) or CD (upper), taken from
                the AWG specified in the command
            val: false, true
        """
        letter = str(self._arbitrary_generator)
        setdict = {'false':0, 'true':1}
        val = setdict[input]
        board = ''
        if letter == 'a' or letter == 'b':
            board = 'AB'
        else:
            board = 'CD'
        self.write(f'C AWG-{board} ONLY {val}')

    def _block_get(self):
        """
        Command to get whether when running an
        AWG blocks all non-AWG behavior on that
        same respective board

        Args:
            letter: Which AWG and thus which board
                is being called, taken from the
                AWG specified in the command
        """
        letter = str(self._arbitrary_generator)
        if letter == 'a' or letter == 'b':
            return self.write(f"C AWG-AB ONLY?")
        else:
            return self.write(f"C AWG-CD ONLY?")
        
    def _clock_set(self, input):
        """
        Command to set the clock period of a board,
        
        Args:
            letter: which AWG is being referenced,
                thus giving the board to be referenced
            val: clock value to be set
        """
        letter = str(self._arbitrary_generator)
        board = ''
        if letter == 'a' or letter == 'b':
            board = 'AB'
        else:
            board = 'CD'
        self.write(f'C AWG-{board} CP {input}')

    def _clock_get(self):
        """
        Command to get the clock period of a board

        Args:
            letter: which AWG is being referenced,
                thus giving the board to be referenced
            val: clock period that is read
        """
        letter = str(self._arbitrary_generator)
        if letter == 'a' or letter == 'b':
            return self.write(f'C AWG-AB CP?')
        else:
            return self.write(f'C AWG-CD CP?')

    def _set_control(self, input):
        """
        Command to set an awg to start or stop.
        A delay is added to allow the awg helper
        function to run without any added delays.
        The cache clearing aspect is added to avoid
        any jumps in voltage to previous selected
        channel voltage values.

        Args:
            input: START/STOP
        """

        awg_num = self.selchan()
        chan = self.parent.channels[awg_num - 1]
        if input == 'START':
            chan.volt.cache._update_with(value=None, raw_value=None)
            time.sleep(0.2) # HACK: needed in practice before playing a waveform

        return self.write(f'C AWG-{self._arbitrary_generator} {input}')

    #Parsers for AWG Functionality
    def _block_get_parser(self, input):
        """
        Parser to get the result of the
        board containing the specified AWG
        in regards to blocking non-AWG
        activity on the board

        Args:
            val: false, true
        """
        dict = {'0':'false', '1':'true'}
        return dict[input]

    def _state_get_parser(self, stateval):
        """
        Parser to get the state of the AWG
        Args:
            val: Idle, Running
        """
        dict = {'0':'Idle',
                '1':'Running'
                }
        return dict[stateval]
    
    def _ava_get_parser(self, avaval):
        """
        Parser to get the availability
        of the selected channel
        Args:
            val: false, true
        """
        dict = {'0':'false',
                '1':'true'
                }
        return dict[avaval]
    
    def _mhz_set_parser(self, input):
        """
        Parser to set the 1MHz clock
        to be on or off
        Args:
            val: off, on
        """
        dict = {'off':0, 'on':1}
        return dict[input]

    def _mhz_get_parser(self, input):
        """
        Parser to get whether the 
        1MHz clock is either on or off
        """
        dict = {'0':'off', '1':'on'}
        return dict[input]


class SWG(InstrumentChannel, SP1060Reader):
    """Defines the class of SWG functionality
    
    Defines the standard waveform generation commands
    of the dac. Separate to the AWG commands in
    structure and thus relegated to a separate class
    to retain this structure

    Attributes:
        mode: String to set/get SWG to generate a waveform
            from user-given aspects or produce a waveform
            saved to WAV-S
        wave: String to set/get the waveform to produce
        freq: Float to set/get the frequency of the waveform
        clockset: String to set/get the clock period to
            generate the waveform as either the AWG clock
            period of the board in question or to adapt
            the board clock period to best fit the user
            specified frequency (the latter option does change
            the value for the entire board and thus may affect
            the other AWG on the board)
        amp: Float to set/get the amplitude of the waveform.
            Range of [-50V, 50V] to allow for unusual clipping
            waveforms as desired, negative voltage is interpreted
            as a phase shift of 180 degrees
        offset: Float to set/get the DC voltage offset
        phase: Float to set/get phase shift of the waveform (not
            applicable for DC voltage only, Gaussian, and Ramp)
        pulse: Float to set/get the duration of the Pulse waveform
            when applicable. Units of percent and range of [0,100],
            a value of 50 yields a square wave
        size: Get the size of the user specified waveform and thus the
            necessary memory to store/produce it
        closefreq: Get the closest AWG frequency to the user-specified
            frequency given the clockset value (this will be the
            frequency outputted, if vastly different than specified
            frequency then select 'adapt' in  clockset)
        clip: Get if the user specified waveform exceeds the maximum
            voltage of [-10V,10V] anywhere, returns true if so
        clock: Get the clock period actually used for the standard
            waveform generation (may differ from clock in AWG if
            adapt is selected in SWG)
        selwm: String to set/get the wave memory to save the user specified
            waveform to (WAV-A/B/C/D, clock period will be saved as well)
        selfunc: String to set/get the wave function dictating how the
            user specified waveform will be saved to the user specified wave memory
            (e.g. simply copied, appended to the end of the memory, etc.)
        lin: String to set/get whether the user specified channel as
            specified in AWG is remembered with the waveform to then
            be utilized in AWG memory if the waveform is copied over
            (this is also true when applying the polynomial) [???]
    """
    def __init__(self, parent, name, standard_wg):
        """Initializes the SWG commands, does not require any user inputs

        Args:
            mode: String to set/get SWG to generate a waveform
                from user-given aspects or produce a waveform
                saved to WAV-S
            wave: String to set/get the waveform to produce
            freq: Float to set/get the frequency of the waveform
            clockset: String to set/get the clock period to
                generate the waveform as either the AWG clock
                period of the board (lower or higher) or to adapt
                to best fit the specified frequency
            amp: Float to set/get the amplitude of the waveform.
                Range of [-50V, 50V] to allow for unusual clipping
                waveforms as desired, negative voltage is interpreted
                as a phase shift of 180 degrees
            offset: Float to set/get the DC voltage offset
            phase: Float to set/get phase shift of the waveform (not
                applicable for DC voltage only, Gaussian, and Ramp)
            pulse: Float to set/get the duration of the Pulse waveform
                when applicable. Units of percent and range of [0,100],
                a value of 50 yields a square wave
            size: Get the size of the user specified waveform and thus the
                necessary memory to store/produce it
            closefreq: Get the closest AWG frequency to the user-specified
                frequency given the clockset value (this will be the
                frequency outputted, if vastly different than specified
                frequency then select 'adapt' in  clockset)
            clip: Get if the user specified waveform exceeds the maximum
                voltage of [-10V,10V] anywhere, returns true if so
            clock: Get the clock period used for the standard waveform
                generation, reflects the same clock periods as clockset
            selwm: String to set/get the wave memory to save the user specified
                waveform to (WAV-A/B/C/D, clock period will be saved as well)
            selfunc: String to set/get the wave function dictating how the
                user specified waveform will be saved to the user specified wave memory
                (e.g. simply copied, appended to the end of the memory, etc.)
            lin: String to set/get whether the user specified channel as
                specified in AWG is remembered with the waveform to then
                be utilized in AWG memory if the waveform is copied over
                (this is also true when applying the polynomial) [???]
        """
        super().__init__(parent, name)
        
        #something else here?

        self.mode: Parameter = self.add_parameter('mode',
                                label = f'{name} mode',
                                set_cmd = f'C SWG MODE {{}}',
                                get_cmd = f'C SWG MODE?',
                                set_parser = self._mode_set_parser,
                                get_parser = self._mode_get_parser
                                )
        
        self.wave: Parameter = self.add_parameter('wave',
                                label = f'{name} wave',
                                set_cmd = f'C SWG WF {{}}',
                                get_cmd = f'C SWG WF?',
                                set_parser = self._wave_set_parser,
                                get_parser = self._wave_get_parser
                                )
        
        self.freq: Parameter = self.add_parameter('freq',
                                label = f'{name} freq',
                                unit = 'Hz',
                                set_cmd = f'C SWG DF {{}}',
                                get_cmd = f'C SWG DF?',
                                get_parser = float,
                                vals = vals.Numbers(0.001, 10000)
                                )
        
        self.clockset: Parameter = self.add_parameter('clockset',
                                label = f'{name} clockset',
                                set_cmd = f'C SWG ACLK {{}}',
                                get_cmd = f'C SWG ACLK?',
                                set_parser = self._clockset_set_parser,
                                get_parser = self._clockset_get_parser
                                )
        
        self.amp: Parameter = self.add_parameter('amp',
                                label = f'{name} amp',
                                unit = 'Vp',
                                set_cmd = f'C SWG AMP {{}}',
                                get_cmd = f'C SWG AMP?',
                                get_parser = float,
                                vals = vals.Numbers(-50, 50)
                                )
        
        self.offset: Parameter = self.add_parameter('offset',
                                label = f'{name} offset',
                                unit = 'V',
                                set_cmd = f'C SWG DCV {{}}',
                                get_cmd = f'C SWG DCV?',
                                get_parser = float,
                                vals = vals.Numbers(-10, 10)
                                )
        
        self.phase: Parameter = self.add_parameter('phase',
                                label = f'{name} phase',
                                unit = 'Degrees',
                                set_cmd = f'C SWG PHA {{}}',
                                get_cmd = f'C SWG PHA?',
                                get_parser = float,
                                vals = vals.Numbers(-360, 360)
                                )
        
        self.pulse: Parameter = self.add_parameter('pulse',
                                label = f'{name} pulse',
                                unit = '%',
                                set_cmd = f'C SWG DUC {{}}',
                                get_cmd = f'C SWG DUC?',
                                get_parser = float,
                                vals = vals.Numbers(0,100)
                                )
        
        self.size: Parameter = self.add_parameter('size',
                                label = f'{name} size',
                                get_cmd = f'C SWG MS?',
                                get_parser = int,
                                vals = vals.Ints(10, 34000)
                                )

        self.closefreq: Parameter = self.add_parameter('closefreq',
                                label = f'{name} closefreq',
                                unit = 'Hz',
                                get_cmd = f'C SWG NF?',
                                get_parser = float,
                                vals = vals.Numbers(0.001, 10000)
                                )
        
        self.clip: Parameter = self.add_parameter('clip',
                                label = f'{name} clip',
                                get_cmd = f'C SWG CLP?',
                                get_parser = self._clip_get_parser
                                )
        
        self.clock: Parameter = self.add_parameter('clock',
                                label = f'{name} clock',
                                unit = 'microseconds',
                                get_cmd = f'C SWG CP?',
                                get_parser = int,
                                vals = vals.Ints(10, 4000000000)
                                )
        
        self.selwm: Parameter = self.add_parameter('selwm',
                                label = f'{name} selwm',
                                set_cmd = f'C SWG WMEM {{}}',
                                get_cmd = f'C SWG WMEM?',
                                set_parser = self._selwm_set_parser,
                                get_parser = self._selwm_get_parser
                                )

        self.selfunc: Parameter = self.add_parameter('selfunc',
                                label = f'{name} selfunc',
                                set_cmd = f'C SWG WFUN {{}}',
                                get_cmd = f'C SWG WFUN?',
                                set_parser = self._selfunc_set_parser,
                                get_parser = self._selfunc_get_parser
                                )

        self.lin: Parameter = self.add_parameter('lin',
                                label = f'{name} lin',
                                set_cmd = f'C SWG LIN {{}}',
                                get_cmd = f'C SWG LIN?',
                                set_parser = self._lin_set_parser,
                                get_parser = self._lin_get_parser
                                )

    #Methods
    def apply(self):
        """
        Command to actually use the user specified wave
        function and save the user specified waveform to
        the user specified wave memory slot. If this
        command is not used, the waveform will not be
        saved to any wave memory. Delay added to ensure
        entire waveform is saved before copying further

        Args:
            N/A
        """
        self.write(f'C SWG APPLY')
        time.sleep(0.2) # HACK: needed in practice after applying a waveform

    #Parsers for the attributes
    def _mode_set_parser(self, modeval):
        """
        Parser to set the user specified mode
        of the SWG
        
        Args:
            val: generate, saved
        """
        dict = {'generate':0, 'saved':1}
        return dict[modeval]
    
    def _mode_get_parser(self, modeval):
        """
        Parser to get the user specified mode
        of the SWG

        Args:
            val: generate, saved
        """
        dict = {'0':'generate',
                '1':'saved'
                }
        return dict[modeval]

    def _wave_set_parser(self, waveval):
        """
        Parser to set the user specified waveform

        Args:
            val: sine, triangle, sawtooth, ramp,
                pulse, fixedgaussian,
                randomgaussian, dc
        """
        dict = {'sine':0,
                'triangle':1,
                'sawtooth':2,
                'ramp':3,
                'pulse':4,
                'fixedgaussian':5,
                'randomgaussian':6,
                'dc':7
                }
        return dict[waveval]
    
    def _wave_get_parser(self, waveval):
        """
        Parser to get the user specified waveform

        Args:
            val: sine, triangle, sawtooth, ramp,
                pulse, fixedgaussian,
                randomgaussian, dc
        """
        dict = {'0':'sine',
                '1':'triangle',
                '2':'sawtooth',
                '3':'ramp',
                '4':'pulse',
                '5':'fixedgaussian',
                '6':'randomgaussian',
                '7':'dc'
                }
        return dict[waveval]
    
    def _clockset_set_parser(self, clockval):
        """
        Parser to set the clock period to either
        be the board's dictated period or to vary
        to fit the user specified frequency

        Args:
            val: keep, adapt
        """
        dict = {'keep':0,
                'adapt':1
                }
        return dict[clockval]
    
    def _clockset_get_parser(self, clockval):
        """
        Parser to get whether the clock period is
        the board's period or to vary to fit the
        user specified frequency

        Args:
            val: keep, adapt
        """
        dict = {'0':'keep',
                '1':'adapt'
                }
        return dict[clockval]
    
    def _clip_get_parser(self, clipval):
        """
        Parser to get whether the user specified
        waveform clips out of the [-10V,10V]
        possible range to output

        Args:
            val: false, true
        """
        dict = {'0':'false',
                '1':'true'
                }
        return dict[clipval]
    
    def _selwm_set_parser(self, selwmval):
        """
        Parser to set the selected wave memory
        to save the user specified waveform to

        Args:
            val: a, b, c, d
        """
        dict = {'a':0,
                'b':1,
                'c':2,
                'd':3
                }
        return dict[selwmval]
    
    def _selwm_get_parser(self, selwmval):
        """
        Parser to get the selected wave memory
        to save the user specified waveform to

        Args:
            val: a, b, c, d
        """
        dict = {'0':'a',
                '1':'b',
                '2':'c',
                '3':'d'
                }
        return dict[selwmval]
    
    def _selfunc_set_parser(self, selfuncval):
        """
        Parser to set the wavefunction that dictates
        how to save the user specified waveform to the
        user specified wave memory

        Args:
            val: copy, startappend, endappend, startsum,
                endsum, startmult, endmult, startdivide,
                enddivide
        """
        dict = {'copy':0,
                'startappend':1,
                'endappend':2,
                'startsum':3,
                'endsum':4,
                'startmult':5,
                'endmult':6,
                'startdivide':7,
                'enddivide':8
                }
        return dict[selfuncval]
    
    def _selfunc_get_parser(self, selfuncval):
        """
        Parser to get the wavefunction dictating how
        to save the user specified waveform to the
        user specified wave memory

        Args:
            val: copy, startappend, endappend, startsum,
                endsum, startmult. endmult, startdivide,
                enddivide
        """
        webster = {'0':'copy',
                   '1':'startappend',
                   '2':'endappend',
                   '3':'startsum',
                   '4':'endsum',
                   '5':'startmult',
                   '6':'endmult',
                   '7':'startdivide',
                   '8':'enddivide'
                   }
        return webster[selfuncval]
    
    def _lin_set_parser(self, linval):
        """
        Parser to set whether to linearize

        Args:
            val: false, true
        """
        dict = {'false':0, 'true':1}
        return dict[linval]

    def _lin_get_parser(self, linval):
        """
        Parser to get whether to linearize

        Args:
            val: false, true
        """
        dict = {'0':'false', '1':'true'}
        return dict[linval]


class WAV(InstrumentChannel, SP1060Reader):
    """Defines the class of WAV functionality

    Defines all of the commands for the wave memories,
    including copying them to AWG memory. Defined as a
    separate class to differentiate the four (technically
    five) wave memories of WAV-A/B/C/D/S

    Attributes:
        memsize: Get the size of any wave memory, WAV-A/B/C/D/S
            (an integer from 0 to 34000). To ensure smooth running,
            clean unused memories
        lin: Gets the channel used when the waveform was saved if
            linearization was true when saved (if it was false,
            the channel is given as 0). This thus records the
            channel for linearization which is applied when
            the wave memory is copied to the corresponding AWG memory (?)
        busy: Get if the wave memory is busy. This only occurs when
            a wave memory is copying its saved waveform to the 
            corresponding AWG memory
    """
    def __init__(self, parent, name, wave_mem):
        """Initializes the wave memory commands without any user inputs

        Args:
            memsize: Get the size of any wave memory, WAV-A/B/C/D/S
                (an integer from 0 to 34000). To ensure smooth running,
                clean unused memories
            lin: Gets the channel used when the waveform was saved if
                linearization was true when saved (if it was false,
                the channel is given as 0). This thus records the
                channel for linearization which is applied when
                the wave memory is copied to the corresponding AWG memory (?)
            busy: Get if the wave memory is busy. This only occurs when
                a wave memory is copying its saved waveform to the 
                corresponding AWG memory
        """
        super().__init__(parent, name)

        self._wave_mem = wave_mem

        self.memsize: Parameter = self.add_parameter('memsize',
                                label = f'{name} memsize',
                                get_cmd = f'C WAV-{wave_mem} MS?',
                                get_parser = int,
                                vals = vals.Ints(0, 34000)
                                )

        self.lin: Parameter = self.add_parameter('lin',
                                label = f'{name} lin',
                                get_cmd = f'C WAV-{wave_mem} LINCH?',
                                get_parser = int,
                                vals = vals.Ints(0, 24)
                                )

        self.busy: Parameter = self.add_parameter('busy',
                                label = f'{name} busy',
                                get_cmd = f'C WAV-{wave_mem} BUSY?',
                                get_parser = self._busy_get_parser
                                )

    
    #methods
    def clear(self):
        """
        Command to clear the specified wave memory

        Args:
            N/A
        """
        self.write(f'C WAV-{self._wave_mem} CLR')

    def save(self):
        """
        Command to save the selected wave memory
        to WAV-S (thus cannot be used with wms)

        Args:
            N/A
        """
        self.write(f'C WAV-{self._wave_mem} SAVE')

    def toawg(self):
        """
        Command to copy the selected wave memory to the
        corresponding AWG memory (eg WAV-A --> AWG-A)
        and thus this command cannot be used on WAV-S

        Args:
            N/A
        """
        self.write(f'C WAV-{self._wave_mem} WRITE')



    #parsers
    def _busy_get_parser(self, input):
        """
        Parser to get whether the selected wave
        memory is busy

        Args:
            val: idle, busy
        """
        dict = {'0':'idle', '1':'busy'}
        return dict[input]


class Board(InstrumentChannel, SP1060Reader):
    """Defines the Board functionalities

    Class to define the upper and lower boards. Allows
    for simple structure behind syncing commands and
    settings

    Attributes:
        update: String to set/get the mode the DAC is in.
            Instant mode immediately transforms written
            DAC values into output voltage (akin to DAC
            mode in the Channel class), and sync mode
            registers written DAC values to be instantly
            applied once a sync command is received.
            For this attribute, the boards must be
            referred to independently and not simultaneously
    """
    def __init__(self, parent, name, board):
        """Initializes the parameters without user input

        Args:
            update: String to set/get the mode the DAC is in.
                Instant mode immediately transforms written
                DAC values into output voltage (akin to DAC
                mode in the Channel class), and sync mode
                registers written DAC values to be instantly
                applied once a sync command is received.
                For this attribute, the boards must be
                referred to independently and not simultaneously
        """
        super().__init__(parent, name)

        self._board = board

        
        self.update: Parameter = self.add_parameter('update',
                                label = f'{name} update',
                                set_cmd = self._update_set,
                                get_cmd = self._update_get,
                                get_parser = self._update_get_parser
                                )
    
    #commands
    def _update_set(self, input):
        """
        Command to set the mode of the board

        Args:
            val: instant, sync
        """
        board = str(self._board)
        dict = {'instant':0, 'sync':1}
        val = dict[input]
        return self.write(f'C UM-{board} {val}')

    def _update_get(self):
        """
        Command to get the mode of the board

        Args:
            N/A
        """
        board = str(self._board)
        return self.write(f'C UM-{board}?')

    #methods
    def sync(self):
        """
        Method to give a sync command to a single
        board or both boards simultaneously

        Args:
            N/A
        """
        board = str(self._board)
        return self.write(f'C SYNC-{board}')

    #parsers
    def _update_get_parser(self, input):
        """
        Parser to get the mode of the board

        Args:
            val: instant, sync
        """
        dict = {'0':'instant', '1':'sync'}
        return dict[input]


class SP1060(VisaInstrument, SP1060Reader):
    """
    QCoDeS driver for the Basel Precision Instruments SP1060 LNHR DAC
    https://www.baspi.ch/low-noise-high-resolution-dac
    
    [[[add onto this?]]]
    """
    
    def __init__(self, name, address, min_val=-10, max_val=10, baud_rate=115200, 
                 voltage_post_delay=0.02, voltage_step=0.01, num_chans=24,**kwargs):
        """
        Creates an instance of the SP1060 24 channel LNHR DAC instrument.
        Args:
            name (str): What this instrument is called locally.
            port (str): The address of the DAC. For a serial port this is ASRLn::INSTR
                        where n is replaced with the address set in the VISA control panel.
                        Baud rate and other serial parameters must also be set in the VISA control
                        panel.
            min_val (number): The minimum value in volts that can be output by the DAC.
            max_val (number): The maximum value in volts that can be output by the DAC.
        
        [[[add onto this?]]]
        """
        super().__init__(name, address, **kwargs)

        # Serial port properties
        handle = self.visa_handle
        handle.baud_rate = baud_rate
        handle.parity = visa.constants.Parity.none
        handle.stop_bits = visa.constants.StopBits.one
        handle.data_bits = 8
        handle.flow_control = visa.constants.VI_ASRL_FLOW_XON_XOFF
        handle.write_termination = '\r\n'
        handle.read_termination = '\r\n'


        """
        Define channels in qcodes corresponding to the channels
        of the SP1060 (12 or 24). These can be accessed by
        SP1060.ch[number] for their attributes, or SP1060.channels
        can be used to see all of the channels qcodes defined
        (this will list the channels as SP1060.chan[number] but
        this is to differentiate the names)
        """
        channels = ChannelList(self, 
                               "Channels", 
                               SP1060Channel, 
                               snapshotable = False,
                               multichan_paramclass = SP1060MultiChannel)
        self.num_chans = num_chans
        for i in range(1, 1+self.num_chans):
            channel = SP1060Channel(self, 'chan{:1}'.format(i), i, 
                                    voltage_post_delay=voltage_post_delay, 
                                    voltage_step=voltage_step,
                                    min_val = min_val,
                                    max_val = max_val)
            channels.append(channel)
            self.add_submodule('ch{:1}'.format(i), channel)
        channels.lock()
        self.add_submodule('channels', channels)
        
        
        """
        Define ramp generators in qcodes corresponding to
        the ramp generators in the SP1060. There are 4 ramp
        generators regardless of 12/24 channels. These can
        be accessed via SP1060.ramp[lowercase letter] for
        attributes or SP1060.ramp_generators for the list
        of the 4 ramp generators (which will be listed as
        SP1060.ramp[lowercase letter])
        """
        generators = ChannelList(self,
                                      "Generators",
                                      RampGenerator,
                                      snapshotable = False,
                                      multichan_paramclass = None
                                      )
        ramp_gens = ('a', 'b', 'c', 'd')
        for i in range(0,4):
            generator = RampGenerator(self, 'ramp{:1}'.format(ramp_gens[i]), ramp_gens[i])
            generators.append(generator)
            self.add_submodule('ramp{:1}'.format(ramp_gens[i]), generator)
        generators.lock()
        self.add_submodule('ramp_generators', generators)


        """
        Defines arbitrary wavefunction generators (AWGs)
        to fit the channels of the instrument (12 or 24).
        There will therefore be 2 or 4 present. These
        can be accessed by SP1060.awg[lowercase letter]
        for attributes or SP1060.aw_generators for a list
        of the AWGs (appearing as SP1060.awgens[lowercase
        letter]). Only AWG-A/B can access channels 1-12
        and similarly AWG-C/D for 13-24
        """
        arbitrary_generators = ChannelList(self,
                                      "Arbitrary_Generators",
                                      AWG,
                                      snapshotable = False,
                                      multichan_paramclass = None
                                      )
        aw_gens = ('a', 'b', 'c', 'd')
        for i in range (0, int(num_chans/6)):
            arbitrary_generator = AWG(self, 'awgens{:1}'.format(aw_gens[i]), aw_gens[i])
            arbitrary_generators.append(arbitrary_generator)
            self.add_submodule('awg{:1}'.format(aw_gens[i]), arbitrary_generator)
        arbitrary_generators.lock()
        self.add_submodule('aw_generators', arbitrary_generators)
        

        """
        Defines a standard wavefunction generator (SWG).
        While not physical, the attributes contained in
        this generator are separate from the AWG to
        differentiate them. Since these attributes can
        be used for all AWGs, only one SWG thus needs
        to be defined. The SWG can be accessed via
        SP1060.swg for attributes and by
        SP1060.sw_generators to see the list of one SWG
        """
        standard_wgs = ChannelList(self,
                                "Standard Waveform Generator",
                                SWG,
                                snapshotable = False,
                                multichan_paramclass = None
                                )
        for i in range(0,1):
            standard_wg = SWG(self, 'swgen', i)
            standard_wgs.append(standard_wg)
            self.add_submodule('swg', standard_wg)
        standard_wgs.lock()
        self.add_submodule('sw_generators', standard_wgs)
        

        """
        Defines the wave memories (WAV) A/B/C/D/S.
        These memories can be accessed for attributes
        via SP1060.wm[letter] and for the list via
        SP1060.wm[letter]
        """
        wave_mems = ChannelList(self,
                                "Wave Memories",
                                WAV,
                                snapshotable = False,
                                multichan_paramclass = None
                                )
        wave_mem_s = ('s', 'a', 'b', 'c', 'd')
        for i in range (0, 4 + 1):
            wave_mem = WAV(self, 'wmems{:1}'.format(wave_mem_s[i]), wave_mem_s[i])
            wave_mems.append(wave_mem)
            self.add_submodule('wm{:1}'.format(wave_mem_s[i]), wave_mem)
        wave_mems.lock()
        self.add_submodule('w_memories', wave_mems)


        """
        Defines boards for the dac. This is to
        simplify some board commands such as sync
        updates that pull the specification of
        the board in the command. To access them
        for such attributes, use SP1060.board[letter]
        and for the list use SP1060.boards. Note
        that "both" is 'lh' but that it can only
        be received for a sync command and cannot
        be used for setting the update of each board
        """
        board_s = ChannelList(self,
                              "Boards",
                              Board,
                              snapshotable = False,
                              multichan_paramclass = None
                              )
        boardlist = ('l', 'h', 'lh')
        for i in range (0, 3):
            board = Board(self, 'board{:1}'.format(boardlist[i]), boardlist[i])
            board_s.append(board)
            self.add_submodule('board{:1}'.format(boardlist[i]), board)
        board_s.lock()
        self.add_submodule('boards', board_s)
        




        # # switch all channels ON if still OFF
        # if 'OFF' in self.query_all():
        #     self.all_on()
            
        self.connect_message()
        print('Current DAC output: ' +  str(self.channels[:].volt.get()))

    """
    A helper function to produce a sine wave from
    AWG-A to channel 12 with user specified frequency
    and amplitude
    """
    def awghelper(self, frequency, amplitude):
        self.swg.mode('generate')
        self.swg.wave('sine')
        self.swg.freq(frequency)
        self.swg.amp(amplitude)
        self.swg.selwm('a')
        self.swg.selfunc('copy')
        self.awga.selchan(12)
        self.swg.lin('true')
        self.swg.apply()
        self.wma.toawg()
        self.ch12.status('ON')
        self.awga.control('START')

    """
    A helper function to produce a 3 cycle ramp out
    of channel 1 from RMP-A with user specified
    voltage range and period
    """
    def ramphelper(self, start, stop, period, channel=1, shape='sawtooth', mode='ramp', cycles=3):
        self.rampa.start(start)
        self.rampa.stop(stop)
        self.rampa.shape(shape)
        self.rampa.selchan(channel)
        self.rampa.period(period)
        self.rampa.cycles(cycles)
        self.rampa.mode(mode)
        self.rampa.control('START')

    """
    channel helper function
    """
    def chhelper(self, amplitude, bw='LBW'):
        self.ch1.status('ON')
        self.ch1.bw(bw)
        self.ch1.volt(amplitude)

    """
    registered channel helper function
    """
    def rghelper(self, volt1, volt2, volt3):
        self.boardl.update('sync')
        self.ch1.status('ON')
        self.ch2.status('ON')
        self.ch3.status('ON')
        self.ch1.volt(volt1)
        self.ch2.volt(volt2)
        self.ch3.volt(volt3)
        self.boardl.sync()


    
    
    
    """
    Below this was provided by BASPI
    """
    def set_all(self, volt):
        """
        Set all dac channels to a specific voltage.
        """
        for chan in self.channels:
            chan.volt.set(volt)
    
    def query_all(self):
        """
        Query status of all DAC channels
        """
        reply = self.write('All S?')
        print(reply)
        return reply.replace("\r\n","").split(';')
    
    def all_on(self):
        """
        Turn on all channels.
        """
        return self.write('ALL ON')
      
    def all_off(self):
        """
        Turn off all channels.
        """
        return self.write('ALL OFF')
    
    def empty_buffer(self):
        # make sure every reply was read from the DAC 
       # while self.visa_handle.bytes_in_buffer:
       #     print(self.visa_handle.bytes_in_buffer)
       #     print("Unread bytes in the buffer of DAC SP1060 have been found. Reading the buffer ...")
       #     print(self.visa_handle.read_raw())
       #      self.visa_handle.read_raw()
       #     print("... done")
        self.visa_handle.clear() 
          
    def write(self, cmd):
        """
        Since there is always a return code from the instrument, we use ask instead of write
        TODO: interpret the return code (0: no error)
        """
        # make sure there is nothing in the buffer
        self.empty_buffer()  
        
        return self.ask(cmd)
    
    def get_serial(self):
        """
        Returns the serial number of the device
        Note that when querying "HARD?" multiple statements, each terminated
        by \r\n are returned, i.e. the device`s reply is not terminated with 
        the first \n received
        """
        self.write('HARD?')
        reply = self.visa_handle.read()
        time.sleep(0.01)
       # while self.visa_handle.bytes_in_buffer:
       #     self.visa_handle.read_raw()
       #     time.sleep(0.01)
        self.empty_buffer()
        return reply.strip()[3:]
    
    def get_firmware(self):
        """
        Returns the firmware of the device
        Note that when querying "HARD?" multiple statements, each terminated
        by \r\n are returned, i.e. the device`s reply is not terminated with 
        the first \n received
        """
        self.write('SOFT?')
        reply = self.visa_handle.read()
        time.sleep(0.01)
       # while self.visa_handle.bytes_in_buffer:
       #     self.visa_handle.read_raw()
       #     time.sleep(0.01)
        self.empty_buffer()
        return reply.strip()[-5:]
        
    
    def get_idn(self):
        SN = self.get_serial()
        FW = self.get_firmware()
        return dict(zip(('vendor', 'model', 'serial', 'firmware'), 
                        ('BasPI', 'LNHR DAC SP1060', SN, FW)))
                        

#reference this
    def set_newWaveform(self, channel = '12', waveform = '0', frequency = '100.0', 
                        amplitude = '5.0', wavemem = '0'):
        """
        Write the Standard Waveform Function to be generated
        - Channel: [1 ... 24]
        Note: AWG-A and AWG-B only DAC-Channel[1...12], AWG-C and AWG-D only DAC-Channel[13...24]
        - Waveforms: 
            0 = Sine function, for a Cosine function select a Phase [°] of 90°
            1 = Triangle function
            2 = Sawtooth function
            3 = Ramp function
            4 = Pulse function, the parameter Duty-Cycle is applied
            5 = Gaussian Noise (Fixed), always the same seed for the random/noise-generator
            6 = Gaussian Noise (Random), random seed for the random/noise-generator
            7 = DC-Voltage only, a fixed voltage is generated
        - Frequency: AWG-Frequency [0.001 ... 10.000]
        - Amplitude: [-50.000000 ... 50.000000]
        - Wave-Memory (WAV-A/B/C/D) are represented by 0/1/2/3 respectively
        """
        memsave = ''
        if (wavemem == '0'):
            memsave = 'A'
        elif (wavemem == '1'):
            memsave = 'B'
        elif (wavemem == '2'):
            memsave = 'C'
        elif (wavemem == '3'):
            memsave = 'D'

        sleep_time = 0.02

        self.write('C WAV-B CLR') # Wave-Memory Clear.
        time.sleep(sleep_time)
        self.write('C SWG MODE 0') # generate new Waveform.
        time.sleep(sleep_time)
        self.write('C SWG WF ' + waveform) # set the waveform.
        time.sleep(sleep_time)
        self.write('C SWG DF ' + frequency) # set frequency.
        time.sleep(sleep_time)
        self.write('C SWG AMP ' + amplitude) # set the amplitude.
        time.sleep(sleep_time)
        self.write('C SWG WMEM ' + wavemem) # set the Wave-Memory.
        time.sleep(sleep_time)
        self.write('C SWG WFUN 0') # COPY to Wave-MEM -> Overwrite.
        time.sleep(sleep_time)
        self.write('C SWG LIN ' + channel) # COPY to Wave-MEM -> Overwrite.
        time.sleep(sleep_time)
        self.write('C AWG-' + memsave + ' CH ' + channel) # Write the Selected DAC-Channel for the AWG.
        time.sleep(sleep_time)
        self.write('C SWG APPLY') # Apply Wave-Function to Wave-Memory Now.
        time.sleep(sleep_time)
        self.write('C WAV-' + memsave + ' SAVE') # Save the selected Wave-Memory (WAV-A/B/C/D) to the internal volatile memory.
        time.sleep(sleep_time)
        self.write('C WAV-' + memsave + ' WRITE') # Write the Wave-Memory (WAV-A/B/C/D) to the corresponding AWG-Memory (AWG-A/B/C/D).
        time.sleep(0.5)
        self.write('C AWG-' + memsave + ' START') # Apply Wave-Function to Wave-Memory Now.

    def set_bandwidth(self, chan, code):
            return self.write('{:0} {:1}'.format(chan, code))

    def get_bandwidth(self, chan):
            dac_code = self.write('{:0} BW?'.format(chan))
            return dac_code
        
    def read_mode(self, chan):
            dac_code = self.write('{:0} M?'.format(chan))
            return dac_code

############################################################

#                     SET COMMANDS

############################################################
###  SET commands can be repeated at a maximum of 1KHz (1 msec)

### SET DAC commands always return a numeric response from the device:
    """
    "0" = No error (normal)
    "1" = Invalid DAC-Channel
    "2" = Missing DAC-Value, Status or BW
    "3" = DAC-Value out of range
    "4" = Mistyped
    "5" = Writing not allowed (Ramp/Step-Generator or AWG are running on this DAC-
    Channel)
    """


    """
    Set a specific DAC channel to a specified voltage.
    @chan - integer indicating channel
    @voltage - hexadecimal voltage value
    """
    def set_chan_voltage(self, chan, voltage):
        code = self.write('{:0} {:X}'.format(chan, voltage))
        return self.handleDACSetErrors(code) 

    """
    Set all dac channels to a specific voltage.
    @voltage - hexadecimal voltage value
    """
    def set_all_voltage(self, voltage):
        code = self.write('ALL {:X}'.format(voltage))
        return self.handleDACSetErrors(code) 
    
    """
    turn on the specified channel
    @chan - integer 
    """
    def set_chan_on(self, chan):
        code = self.write('{0} ON'.format(chan))
        return self.handleDACSetErrors(code) 

    """
    turn off the specified channel
    @chan - integer 
    """
    def set_chan_off(self, chan):
        code = self.write('{0} OFF'.format(chan))
        return self.handleDACSetErrors(code) 

    """
    Turn on all channels.
    """
    def set_all_on(self):
        code = self.write('ALL ON')
        return self.handleDACSetErrors(code) 
      
      
    """
    Turn off all channels.
    """
    def set_all_off(self):
        code = self.write('ALL OFF')
        return self.handleDACSetErrors(code) 

    """
    Set the bandwidth of a specified channel (High or Low)
    @chan - integer 
    @code - string ("HBW"/"LBW")
    """
    def set_chan_bandwidth(self, chan, code):
        code = self.write('{} {}'.format(chan, code))
        return self.handleDACSetErrors(code) 
    """
    Set the bandwidth of all channels (High or Low)
    @code - string ("HBW"/"LBW")
    """
    def set_all_bandwidth(self, code):
        code = self.write('ALL {}'.format(code))
        return self.handleDACSetErrors(code) 

#### All AWG SET Commands return a numeric response:
    """
    "0" = No error (normal)
    "1" = Invalid AWG-Memory
    "2" = Missing AWG-Address and/or AWG-Value
    "3" = AWG-Address and/or AWG-Value out of range
    "4" = Mistyped
    """
####

    """
    Set an AWG_memory address to a value
    @mem - character specifiying AWG-memory
    @adr - hexadecimal address
    @value - hexadecimal value of voltage
    """
    def set_adr_AWGmem(self, mem, adr, value):
        code = self.write("AWG-{} {:X} {:X}".format(mem, adr, value))

    def set_all_AWGMem(self, mem, value):
        code = self.write("AWG-{} ALL {:X}".format(mem, value))

#### All WAV SET Commands return a numeric response:
    """
    "0" = No error (normal)
    "1" = Invalid WAV-Memory
    "2" = Missing WAV-Address and/or WAV-Voltage
    "3" = WAV-Address and/or WAV-Voltage out of range
    "4" = Mistyped
    """
####

    """
    Set a WAV-memory address to a value
    @mem - character specifiying WAV-memory
    @adr - hecadecimal address
    @value - hexadecimal value of voltage
    """
    def set_adr_WAVMem(self, mem, adr, value):
        code = self.write("WAV-{0} {:X} {:X}".format(mem, adr, value))

    def set_all_WAVMem(self, mem, value):
        code = self.write("WAV-{0} ALL {:X}".format(mem, value))

#### POLY command return codes:
    """
    "0" = No error (normal)
    "1" = Invalid Polynomial Name
    "2" = Missing Polynomial Coefficient(s)
    "4" = Mistyped
    """
####

    """
    Set polynomial coefficients
    @mem - character of a polynomial memory
    @coefs - list of floating point values representing the coefficients (a0, a1, a2, a3...)
    
    """
    def set_polynomial(self, mem, coefs):
        fs = [str(c) for c in coefs]
        code = self.write('POLY-{} {}'.format(mem, ' '.join(fs)))


############################################################

#                    QUERY DATA COMMANDS

############################################################

    """
    Read the actual voltage of a specified channel
    @chan - integer 
    """
    def query_chan_voltage(self, chan):
        dac_code=self.write('{:0} V?'.format(chan))
        return self._dacval_to_vval(dac_code)

    def query_all_voltage(self):
        dac_code=self.write('ALL V?')
        return dac_code

    """
    Read the registered voltage of a specified channel
    @chan - integer 
    """
    def query_chan_voltageReg(self, chan):
        dac_code=self.write('{:0} VR?'.format(chan))
        return self._dacval_to_vval(dac_code)

    def query_all_voltageReg(self):
        dac_code=self.write('ALL VR?')
        return dac_code


    """
    Query status of a channel
    @chan - integer 
    """
    def query_chan_status(self, chan):
        reply = self.write('{0} S?'.format(chan))
        return reply

    """
    Query status of all DAC channels
    """
    def query_all_status(self):
        reply = self.write('All S?')
        return reply.replace("\r\n","").split(';')
    
    """
    Query a bandwidth of a channel
    @chan - integer specifying channel
    """
    def query_chan_bandwidth(self, chan):
        reply = self.write('{0} BW?'.format(chan))
        return reply

    def query_all_bandwidth(self):
        reply = self.write('ALL BW?')
        return reply.replace("\r\n","").split(';')

    """
    Query a DAC mode
    MODES are ERR/DAC/SYN/RMP/AWG/---
    See section 7.1.10 of programming manual for descriptions
    @chan - integer specifying channel
    """
    def query_chan_DACMode(self, chan):
        reply = self.write('{0} M?'.format(chan))
        return reply
    
    def query_all_DACMode(self):
        reply = self.write('ALL M?')
        return reply.replace("\r\n","").split(';')

#useful?
    """
    Query memory contents of AWG memory at address(es)
    @mem - character indicating AWG memory A/B/C/D
    @adr - hex number indicating address
    """
    def query_adr_AWGmem(self, mem, adr):
        reply = self.write('AWG-{0} {:X}?'.format(mem, adr))
        return reply

    """
    Queries a block of 1,000 AWG hex values starting at block_start
    @mem - character indicating AWG memory A/B/C/D
    @block_start - hex number indicating start address
    """
    def query_block_AWGmem(self, mem, block_start):
        reply = self.write('AWG-{0} {:X} BLK?'.format(mem, block_start))
        return reply.replace("\r\n","").split(';')

    """
    Queries memory contents of WAV memory at address(es)
    @mem - character indicating AWG memory A/B/C/D
    @adr - hex number indicating address
    """
    def query_adr_WAVmem(self, mem, adr):
        reply = self.write('WAV-{0} {:X}?'.format(mem, adr))
        return reply

    """
    Queries a block of 1,000 WAV hex values starting at block_start
    @mem - character indicating AWG memory A/B/C/D
    @block_start - hex number indicating start address
    """
    def query_block_WAVmem(self, mem, block_start):
        reply = self.write('WAV-{0} {:X} BLK?'.format(mem, block_start))
        return reply.replace("\r\n","").split(';')

    """
    Query polynomial coefficients of a poly mem
    @mem - character indicating poly memory A/B/C/D
    """
    def query_coefs_Polymem(self, mem):
        reply = self.write('POLY-{0}?'.format(mem))
        return reply.replace("\r\n","").split(';')

             
############################################################

#                    QUERY INFORMATION COMMANDS

############################################################
    def get_serial(self):
        """
        Returns the serial number of the device
        Note that when querying "HARD?" multiple statements, each terminated
        by \r\n are returned, i.e. the device`s reply is not terminated with 
        the first \n received
        """
        self.write('HARD?')
        reply = self.visa_handle.read()
        time.sleep(0.01)
       # while self.visa_handle.bytes_in_buffer:
       #     self.visa_handle.read_raw()
       #     time.sleep(0.01)
        self.empty_buffer()
        return reply.strip()[3:]

    """
    Returns overview of the ASCII commands and queries
    """
    def get_overview(self):
        reply = self.write('?')
        return reply

    """
    Shows the help text
    """
    def get_help(self):
        reply = self.write("HELP?")
        return reply

    """
    Shows the health of the device (temperature, cpu-load, power-supplies)
    """
    def get_health(self):
        reply = self.write("HEALTH?")
        return reply

    """
    Obtains the IP address of the DAC
    """
    def get_ip(self):
        reply = self.write("IP?")
        return reply

    """
    Provides contact information (name, lab, website, email. phone)
    """
    def get_contact(self):
        reply = self.write("CONTACT?")
        return reply

    
    def get_firmware(self):
        """
        Returns the firmware of the device
        Note that when querying "HARD?" multiple statements, each terminated
        by \r\n are returned, i.e. the device`s reply is not terminated with 
        the first \n received
        """
        self.write('SOFT?')
        reply = self.visa_handle.read()
        time.sleep(0.01)
       # while self.visa_handle.bytes_in_buffer:
       #     self.visa_handle.read_raw()
       #     time.sleep(0.01)
        self.empty_buffer()
        return reply.strip()[-5:]
        
    """
    Obtain identification numbers and other manufacturer information about the DAC
    """
    def get_idn(self):
        SN = self.get_serial()
        FW = self.get_firmware()
        return dict(zip(('vendor', 'model', 'serial', 'firmware'), 
                        ('BasPI', 'LNHR DAC SP1060', SN, FW)))
                        

######################################################################################

#                  DAC Update-Mode and Synchronization CONTROL COMMANDS

######################################################################################
    """
    Returns the update mode of the device for the given board (higher or lower)
    @board - character, 'H'/'L' for higher or lower board
    """
    def read_updateMode(self, board):
        return self.write("C UM-{}?".format(board))

    """
    Writes the update mode for the higher or lower board.
    @board - character, 'H'/'L' for higher or lower board
    @mode = integer, either 0/1 for instantly/synchronous
    """
    def write_updateMode(self, board, mode):
        self.write("C UM-{} {}".format(board, mode))


    """
    Makes a synchronous DAC-update of all 12 channels on one DAC Board,
    or on both in parallel
    @board - string indicating board(s) to update: "H"/"L"/"HL" for higher/lower/both
    """
    def update_board_sync(self, board):
        return self.write("C SYNC-{}".format(board))

######################################################################################

#                  RAMP/STEP-Generator CONTROL COMMANDS

######################################################################################

    """
    Control the mode of the four RAMP/STEP generators.
    Modes are START, STOP, HOLD.  Ramp memories are A/B/C/D.
    By indicating "ALL" you can control all 4 generators.
    @mem - the ramp memory to control: A/B/C/D/ALL
    @mode - string indicating mode: HOLD/START/STOP
    """
    def write_rampMode(self, mem, mode):
        return self.write("C RMP-{} {}".format(mem, mode))

    """
    Read the state of one ramp generator
    States are Idle/Ramp_UP/Ramp_DOWN/Hold (coded as 0/1/2/3, respectively)
    @mem - character indicating ramp mem: A/B/C/D
    """
    def read_rampState(self, mem):
        return self.write("C RMP-{} S?".format(mem))

    """
    Read the cycles done since the start of the specified ramp generator
    @mem - character indicating ramp mem: A/B/C/D 
    """
    def read_rampCyclesDone(self, mem):
        return self.write("C RMP-{} CD?".format(mem))

    """
    Read the steps done since the start of the specified ramp generator
    @mem - character indicating ramp mem: A/B/C/D 
    """
    def read_rampStepsDone(self, mem):
        return self.write("C RMP-{} SD?".format(mem))

    """
    Reads the step-size voltage of the specified ramp generator
    @mem - character indicating ramp mem: A/B/C/D 
    """
    def read_rampStepSizeVoltage(self, mem):
        return self.write("C RMP-{} SSV?".format(mem))

    """
    Read the calculated step per cycle of a ramp memory.
    @mem - character indicating ramp mem: A/B/C/D
    """
    def read_rampStepsPerCycle(self, mem):
        return self.write("C RMP-{} ST?".format(mem))

    """
    Readout if the selected DAC-Channel of the RAMP/STEP-Generator (RMP-A/B/C/D) is
    available (not used by other RAMP- or AWG-Channels). The returned integer number
    gives the availability:
        0=Not Available/1=Available
    A running generator always reads not available.
    @mem - character indicating ramp mem: A/B/C/D
    """
    def read_rampChannelAvailable(self, mem):
        return self.write("C RMP-{} AVA?".format(mem))

    """
    Read or write the Selected DAC-Channel for the RAMP/STEP-Generator (RMP-A/B/C/D).
    The DAC-Channel can be in the range from 1 to 24. After writing the Selected DAC-
    Channel, its availability can be checked
    @mem - character indicating ramp mem: A/B/C/D 
    @chan - integer specifying the channel
    """
    def read_rampSelectedChannel(self, mem):
        return self.write("C RMP-{} CH?".format(mem))

    def write_rampSelectedChannel(self, mem, chan):
        return self.write("C RMP-{} CH {}".format(mem, chan))
    """
    Read or write the Start Voltages of the RAMP/STEP-Generators (RMP-A/B/C/D). The
    Start Voltage is a floating-point number in the range between -10.000000 V and
    +10.000000 V; the decimal point must be a period (point).
    @mem - character indicating ramp mem: A/B/C/D 
    @voltage - floating point number indicating voltage
    """
    def read_rampStartVoltage(self, mem):
        return self.write("C RMP-{} STAV?".format(mem))

    def write_rampStartVoltage(self, mem, voltage):
        return self.write("C RMP-{} STAV {}".format(mem, voltage))
    """
    Read or write the Stop/Peak Voltages of the RAMP/STEP-Generators (RMP-A/B/C/D).
    The Stop/Peak Voltage is a floating-point number in the range between -10.000000 V and
    +10.000000 V; the decimal point must be a period (point). If the RAMP Shape is UP-ONLY
    (Sawtooth function) this value is the Stop Voltage. If the RAMP Shape is UP and DOWN
    (Triangle function) this value is the Peak Voltage, since the Triangle function returns to
    the Start Voltage.
    @mem - character indicating ramp mem: A/B/C/D 
    @voltage - floating point number indicating voltage
    """
    def read_rampStopPeakVoltage(self, mem):
        return self.write("C RMP-{} STOV?".format(mem))

    def write_rampStopPeakVoltage(self, mem, voltage):
        return self.write("C RMP-{} STOV {}".format(mem, voltage))
    """
    Read or write the RAMP Times of the RAMP/STEP-Generators (RMP-A/B/C/D). The
    RAMP Time is a floating-point number in the range between 0.05 second and 1E6 seconds
    (equal to 277.7 hours); the decimal point must be a period (point). The inherent
    resolution is given by the RAMP/STEP-Generator cycle of 5 msec (0.005 second).
    @mem - character indicating ramp mem: A/B/C/D 
    @time - floating point number of seconds
    """
    def read_rampTime(self, mem):
        return self.write("C RMP-{} RT?".format(mem))

    def write_rampTime(self, mem, time):
        return self.write("C RMP-{} RT {}".format(mem, time))
    """
    Read or write the RAMP Shape of the RAMP/STEP-Generators (RMP-A/B/C/D). Two
    different Shapes of the Ramping/Stepping function can be written or readout:
    0=UP-ONLY (Sawtooth function)/1=UP and DOWN (Triangle function)
    @mem - character indicating ramp mem: A/B/C/D 
    @shape - integer 0/1 indicating shape of RAMP function
    """
    def read_rampShape(self, mem):
        return self.write("C RMP-{} RS?".format(mem))

    def write_rampShape(self, mem, shape):
        return self.write("C RMP-{} RS {}".format(mem, shape))
    """
    Read or write the number of RAMP Cycles-Set (0....4E9) of the four RAMP/STEP-
    Generators (RMP-A/B/C/D). The integer number represents the number of RAMP Cycles-
    Set until the RAMP/STEP-Generator gets stopped. If the number of RAMP Cycles-Set is
    zero (0), an infinite number of RAMP Cycles are done; the RAMP/STEP-Generator runs
    until it is stopped by the user
    @mem - character indicating ramp mem: A/B/C/D 
    @cycles - integer specifying cycles 
    """
    def read_rampCyclesSet(self, mem):
        return self.write("C RMP-{} CS?".format(mem))

    def write_rampCyclesSet(self, mem, cycles):
        return self.write("C RMP-{} CS {}".format(mem, cycles))

    """
    Read or write the RAMP/STEP-Selection of the four RAMP/STEP-Generators (RMP-
    A/B/C/D). The RAMP/STEP-Generators can be switched between RAMP function and
    STEP function. The normal RAMP function periodically updates the DAC-Voltage each
    5 msec. The STEP function updates the DAC-Voltage when the AWG has stopped (single
    cycle); this used for 2D-Scans. The two different functions (RAMP/STEP) can be written
    or readout:
    0=RAMP function/1=STEP function
    @mem - character indicating ramp mem: A/B/C/D 
    @sel - integer indicating selection, 0: RAMP, 1: STEP
    """
    def read_rampStepSelection(self, mem):
        return self.write("C RMP-{} STEP?".format(mem))

    def write_rampStepSelection(self, mem, sel):
        return self.write("C RMP-{} STEP {}".format(mem, sel))



######################################################################################

#                  2D-Scan CONTROL COMMANDS

######################################################################################
    """
    Read or write the Boolean parameter Normal-Start / Auto-Start AWG. If Auto-Start AWG
    is selected (1) the AWG gets automatically restarted after the STEP-Generator has been
    updated. A minimum time delay of 5 msec is implemented from the update of the STEP-
    Generator to the restart of the AWG.
    If Auto-Start AWG is deselected (0) the AWG starts normally by an external TTL-Trigger
    or via a CONTROL Command. The two different modes (Normal-Start AWG or Auto-Start
    AWG) can be written or readout:
    0=Normal-Start AWG/1=Auto-Start AWG
    @mem - character indicating AWG memory A/B/C/D
    @mode - integer of start mode, 0: normal 1: auto
    """
    def read_AWGStartMode(self, mem):
        return self.write("C AWG-{} AS?".format(mem, mode))

    def write_AWGStartMode(self, mem, mode):
        return self.write("C AWG-{} AS {}".format(mem, mode))

    """
    Read or write the Boolean parameter Keep/Reload AWG MEM. If Reload AWG MEM is
    selected (1) the AWG-Memory (AWG-A/B/C/D) is reloaded from the corresponding
    Wave-Memory (WAV-A/B/C/D) before it gets restarted. This is option is slower, but has
    to be selected since the Polynomial (POLY-A/B/C/D) must be applied to perform an
    adaptive 2D-Scan
    If Keep AWG MEM is selected (0) the predefined AWG-Memory is used for a next scan-
    line, which allows a faster 2D-Scan, but without adaption. These two different behaviors
    (Keep AWG MEM or Reload AWG MEM) can be written or readout:
    0=Keep AWG MEM/1=Reload AWG MEM
    @mem - character indicating AWG memory A/B/C/D
    @mode - integer of mode, 0/1 (keep/reload)
    """
    def read_AWGReloadMode(self, mem):
        return self.write("C AWG-{} RLD?".format(mem, mode))

    def write_AWGReloadMode(self, mem, mode):
        return self.write("C AWG-{} RLD {}".format(mem, mode))
    """
    Read or write the Boolean parameter Skip/Apply Polynomial. If Apply Polynomial is
    selected (1) the Polynomial (POLY-A/B/C/D) is applied when the AWG-Memory (AWG-
    A/B/C/D) is reloaded from the corresponding Wave-Memory (WAV-A/B/C/D); this is
    essential for an adaptive 2D-Scan. The Polynomial (POLY-A/B/C/D) can be updated fast
    by using the SET POLY Command or by using the parameter “Adaptive Shift-Voltage” – see
    description below.
    If Skip Polynomial is selected the Polynomial (POLY-A/B/C/D) isn’t applied when the
    predefined Wave-Memory (WAV-A/B/C/D) is written to the AWG-Memory (AWG-
    A/B/C/D). These two different behaviors (Skip Polynomial or Apply Polynomial) can be
    written or readout:
    0=Skip Polynomial/1=Apply Polynomial
    @mam - character of poly memory A/B/C/D
    @mode - ingeger indicating mode 0/1 (skip/apply)
    """
    def read_AWGApplyPolyMode(self, mem):
        return self.write("C AWG-{} AP?".format(mem, mode))

    def write_AWGApplyPolyMode(self, mem, mode):
        return self.write("C AWG-{} AP {}".format(mem, mode))
    """
    Read or write the Adaptive Shift-Voltage per Step of the STEP-Generators (RMP-
    A/B/C/D). A simple adaptive 2D-Scan (with linear y-adaption) can be performed by this
    parameter. This Shift-Voltage gets applied to the AWG function (y-Axis) after each step of
    the STEP-Generator (x-Axis). This is automatically done by linearly modifying the
    polynomial coefficient a 0 (constant) after each step. This coefficient a 0 is calculated by
    multiplying the Adaptive Shift-Voltage by the RAMP Cycles-Done. If the Adaptive Shift-
    Voltage is zero (0) the polynomial will not be changed.
    Since it is allowed to modify this Adaptive Shift-Voltage while a 2D-Scan is running, also
    nonlinear adaptions can be easily implemented.
    The Adaptive Shift-Voltage is a floating-point number in the range between -10.000000 V
    and +10.000000 V per Step; the decimal point must be a period (point).
    @mem - character indicating AWG memory A/B/C/D
    @voltage - floating point number of voltage
    """
    def read_AWGShiftVoltage(self, mem):
        return self.write("C AWG-{} SHIV?".format(mem, mode))

    def write_AWGShiftVoltage(self, mem, voltage):
        return self.write("C AWG-{} SHIV {}".format(mem, voltage))


######################################################################################

#                  AWG CONTROL COMMANDS 

######################################################################################
    """
    Read or write the Boolean parameter AWG Normal/AWG Only, related to the Lower DAC
    Board (AWG-A/B) or to the Higher DAC-Board (AWG-C/D). If AWG Only is selected (1), all
    the other DAC-CHANNELs on this DAC-Board get blocked (---) and only the AWG-Channels
    are active; this results in lower time-jitter for these AWG-Channels.
    If AWG Normal is selected (0) the other DAC-CHANNELs on the corresponding DAC-Board
    are free to be used for normal DAC operation (DAC) or as RAMP/STEP-Generator (RMP).
    These two different options (AWG Normal or AWG Only) can be written or readout:
    0=AWG Normal/1=AWG Only
    @board - string indicating board, AB/CD for lower/higher board
    @mode - integer of mode, 0/1 (awg normal, awg only)
    """
    def read_AWGNormalMode(self, board):
        return self.write("C AWG-{} ONLY?".format(board))

    def write_AWGNormalMode(self, board, mode): 
        return self.write("C AWG-{} ONLY {}".format(board, mode))
    """
    Control the mode of the four AWGs (AWG-A/B/C/D) by the two Boolean controls Start
    and Stop. After setting theses controls, they are reset internally. AWG-AB allows
    synchronous access to the two AWGs on the Lower DAC-Board and AWG-CD to the two
    AWGs on the Higher DAC-Board. AWG-ALL makes synchronous access to all the four
    AWGs. A synchronous start of multiple AWGs (AB/CD/ALL) can only be performed when
    all these AWGs are in Idle-Mode.
    @mem - character indicating the AWG memory or memories A/B/C/D/AB/CD/ALL
    @mode - string indicating control mode, START/STOP
    """
    def write_AWGControlMode(self, mem, mode): 
        return self.write("C AWG-{} {}".format(mem, mode))
    """
    Readout the State (Idle/Running) of the four AWGs (AWG-A/B/C/D). The returned
    integer number defines the actual state:
    0=Idle/1=Running
    @mem - character indicating AWG memory A/B/C/D
    """
    def read_AWGState(self, mem):
        return self.write("C AWG-{} S?".format(mem))

    """
    Readout the AWG Cycles-Done of the four AWGs (AWG-A/B/C/D). The returned integer
    number represents the completed AWG Cycles since the Start; it is in a range from 0 to
    4E9. When the AWG is stopped (state Idle) the AWG Cycles-Done shows the last value;
    when the AWG is started it is reset to zero (0). After power-up all the AWG Cycles-Done
    counters are zero (0)
    @mem - character indicating AWG memory A/B/C/D
    """
    def read_AWGCyclesDone(self, mem): 
        return self.write("C AWG-{} CD?".format(mem))
    """
    Readout the Duration/Period of a complete AWG-Cycle (AWG Memory_Size * AWG Clock-
    Period) of the four AWGs (AWG-A/B/C/D). The unit of the Duration/Period is second
    (sec). The minimum AWG Memory Size is 2 and the minimum AWG Clock-Period is 10E-
    6 sec, resulting in a minimum Duration/Period is 20E-6 sec. The maximum
    Duration/Period of 1.36E8 sec is given by the maximum AWG Memory Size of 34’000 and
    the maximum AWG Clock-Period 4’000 sec (4E9 * 1E-6 sec).
    The Duration/Period is a floating-point/exponential (E) number with a period (point) as
    decimal separator
    @mem - character indicating AWG memory A/B/C/D
    """
    def read_AWGDuration(self, mem):
        return self.write("C AWG-{} DP?".format(mem))
    """
    Readout if the selected DAC-Channel of the AWG (AWG-A/B/C/D) is available (not used
    by other AWG- or RAMP-Channels). The returned integer number gives the availability:
    0=Not Available/1=Available
    Note: A running AWG reads always “Not Available (0)” on its DAC-Channel.
    @mem - character indicating AWG memory A/B/C/D
    """
    def read_AWGChannelAvailable(self, mem): 
        return self.write("C AWG-{} AVA?".format(mem))
    """
    Read or write the Selected DAC-Channel for the AWG (AWG-A/B/C/D). Since the AWG-A
    and the AWG-B are running on the Lower DAC-Board, their DAC-Channels can only be in
    the range from 1 to 12. The AWG-C and the AWG-D are running on the Higher DAC-Board
    and therefor the DAC-Channels are restricted to the range from 13 to 24.
    After writing the Selected DAC-Channel, its availability can be checked
    @mem - character indicating AWG memory A/B/C/D
    @chan - integer of channel
    """
    def read_AWGSelectedChannel(self, mem):
        return self.write("C AWG-{} CH?".format(mem))
    
    def write_AWGSelectedChannel(self, mem, chan): 
        return self.write("C AWG-{} CH {}".format(mem, chan))
    """
    Read or write the AWG-Memory Size of the AWG (AWG-A/B/C/D) which is an integer
    number in the range from 2 to 34’000. Each point of the AWG-Memory corresponds to a
    24-bit DAC-Value.
    The AWG streams this AWG-Memory Size number to the DAC when the AWG is started.
    This is independent of the number of programmed AWG-Memory Addresses. If the user
    has downloaded an AWG-Waveform consisting of 1’000 points, also the AWG-Memory
    Size has to be set to 1’000.
    @mem - character indicating AWG memory A/B/C/D
    @size - integer of memory size
    """
    def read_AWGMemorySize(self, mem):
        return self.write("C AWG-{} MS?".format(mem))

    def write_AWGMemorySize(self, mem, size): 
        return self.write("C AWG-{} MS {}".format(mem, size))
    """
    Read or write the number of AWG Cycles-Set (0....4E9) of one of the four AWGs (AWG-
    A/B/C/D). The integer number represents the number of AWG Cycles-Set until the AWG
    gets stopped. If the number of AWG Cycles-Set is zero (0), an infinite number of AWG-
    Cycles are done; the AWG runs until it is stopped by the user.
    @mem - character indicating AWG memory A/B/C/D
    @cycles - integer of number of cycles
    """
    def read_AWGCyclesSet(self, mem):
        return self.write("C AWG-{} CS?".format(mem))

    def write_AWGCyclesSet(self, mem, cycles): 
        return self.write("C AWG-{} CS {}".format(mem, cycles))
    """
    Read or write the External Trigger Mode of one of the four AWGs (AWG-A/B/C/D). This
    sets the behavior of the four digital inputs “Trig In AWG-A/B/C/D” on the back panel of
    the device. The external applied TTL trigger-signals can be programmed to have the
    following four different functionalities:
    - Disabled (0): The trigger-input has no impact.
    - START only (1): The AWG starts on a rising edge of the TTL-signal.
    - START-STOP (2): The AWG starts on a rising edge and stops on a falling edge.
    - SINGLE-STEP (3): The AWG starts on a rising edge of the TTL-signal and the AWG makes
    a single step for each rising edge. Therefore, the AWG Clock is defined by the external
    applied TTL trigger-signal from DC up to maximum 100 kHz (PW minimum 2 μsec).
    @mem - character indicating AWG memory A/B/C/D
    @mode - integer indicating mode 0/1/2/3 (disabled/START only/START-STOP/SINGLE STEP)
    """
    def read_AWGExtTriggerMode(self, mem):
        return self.write("C AWG-{} TM?".format(mem))

    def write_AWGExtTriggerMode(self, mem, mode): 
        return self.write("C AWG-{} TM {}".format(mem, mode))
    """
    Read or write the Clock-Period [μsec] (10....4E9) of the Lower (AWG-A+B) or the Higher
    DAC-Board (AWG-C+D). This integer number represents the AWG Clock-Period in μsec
    (1E-6 sec) and the minimum is 10 μsec and the maximum 4E9 μsec which corresponds to
    4’000 sec (4E9 * 1E-6 sec). The resolution of the Clock-Period is 1 μsec.
    The Lower AWG Clock-Period [μsec] is common for the AWG-A and the AWG-B, running
    on the Lower DAC-Board. The Higher AWG Clock-Period [μsec] is common for the AWG-C
    and the AWG-D, running on the Higher DAC-Board.
    @board - string indicating AWG board, AB/CD (lower, higher)
    @T - integer specifying period
    """
    def read_AWGClkPeriod(self, board):
        return self.write("C AWG-{} CP?".format(board))

    def write_AWGClkPeriod(self, board, T): 
        return self.write("C AWG-{} CP {}".format(board, T))
    """
    Read or write the Control-Status (ON/OFF) of the external digital AWG 1 MHz Clock
    Reference TTL signal (on the D-SUB connector on the back-panel). This 1 MHz reference
    clock is internally used for the AWGs and it can be used to synchronize other devices with
    the LNHR DAC II
    @mode - integer of mode 0/1 (OFF/ON)
    """
    def read_AWGClkRefState(self):
        return self.write("C AWG-1MHz?")

    def write_AWGClkRefState(self, mode): 
        return self.write("C AWG-1MHz {}".format(mode))


######################################################################################

#                  STANDARD WAVEFORM GENERATION (SWG) CONTROL COMMANDS

######################################################################################
    """
    Read or write the Boolean parameter SWG Mode which can be either “Generate New
    Waveform” (0) or “Use Saved Waveform” (1). When the default Mode “Generate New
    Waveform” is selected, a new waveform can be generated by using the Standard
    Waveforms and the Wave-Functions. In the “Use Saved Waveform” Mode the previously
    saved waveform (WAV-S) is recalled and the selected Wave-Functions can be applied on
    this recalled waveform; e.g., it can be copied to a Wave-Memory (WAV-A/B/C/D).
    @mode - integer of SWG mode 0/1 (use saved waveform/generate new waveform)
    """
    def read_SWGMode(self):
        return self.write("C SWG MODE?")

    def write_SWGMode(self, mode):
        return self.write("C SWG MODE {}".format(mode))
    """
    Read or write the Standard Waveform Function to be generated. The following eight
    different functions can be selected and are represented by these integer numbers:
    0 = Sine function – for a Cosine function select a Phase [°] of 90°
    1 = Triangle function
    2 = Sawtooth function
    3 = Ramp function
    4 = Pulse function – the parameter Duty-Cycle [%] is applied
    5 = Gaussian Noise (Fixed) – always the same seed for the random/noise-generator
    6 = Gaussian Noise (Random) – random seed for the random/noise-generator
    7 = DC-Voltage only – a fixed voltage is generated
    @func - integer specifying function to be written, 0/1/2/3/4/5/6/7 (see above for coding scheme)
    """
    def read_SWGFunction(self):
        return self.write("C SWG WF?")

    def write_SWGFunction(self, func):
        return self.write("C SWG WF {}".format(func))
    """
    Read or write the Desired AWG-Frequency [Hz] of the Wave- and AWG-function.
    Sometimes it isn’t possible to reach exact this frequency; see also “Keep / Adapt AWG
    Clock-Period” and the “Nearest AWG-Frequency [Hz]”. The Desired AWG-Frequency [Hz]
    is a floating-point number in the range between 0.001 Hz and 10’000 Hz; the decimal
    point must be a period (point).
    At the maximum Desired AWG-Frequency of 10’000 Hz (period 100 μsec) the Standard
    Waveform consists of 10 points at an AWG Clock-Period of 10 μsec.
    @freq - floating point number specifying frequency in Hz
    """
    def read_SWGDesFrequency(self):
        return self.write("C SWG DF?")

    def write_SWGDesFrequency(self, freq):
        return self.write("C SWG DF {}".format(freq))
    """
    Read or write the Boolean parameter Keep/Adapt AWG Clock-Period. To reach the
    Desired AWG-Frequency as close as possible, select Adapt AWG Clock-Period.
    If Adapt AWG Clock-Period (1) is selected, the AWG Clock-Period gets adapted to meet the
    Desired AWG Frequency as close as possible. The update of the AWG Clock-Period on the
    corresponding DAC-Board (Lower or Higher) is automatically done, when the Wave-
    Memory is written to the AWG-Memory; see AWG Clock-Period [μsec] in the AWG
    CONTROL Commands.
    If Keep AWG Clock-Period (0) is selected, the AWG Clock-Period of the corresponding
    DAC-Board (depending on the Selected Wave-Memory A/B/C/D) is read and used for the
    waveform generation. At the standard AWG Clock-Period of 10 μsec the minimal AWG
    Frequency is 2.941 Hz; this is given by the maximum AWG-Memory Size of 34’000 points
    times the AWG Clock-Period of 10 μsec. Lower AWG frequencies can be reached by
    selecting higher AWG Clock-Periods.
    These two different options (Keep/Adapt AWG Clock-Period) can be written or readout:
    0=Keep AWG Clock-Period/1=Adapt AWG Clock-Period
    @mode - integer of adaptive clock mode, 0/1 (keep/adapt)
    """
    def read_SWGApdativeClk(self):
        return self.write("C SWG ACLK?")

    def write_SWGAdaptiveClk(self, mode):
        return self.write("C SWG ACLK {}".format(mode))
    """
    Read or write the Amplitude [Vp] parameter of the generated Standard Waveform. This
    value corresponds to the peak-voltage of the generated Standard Waveform. For
    Gaussian-Noise the Amplitude [Vp] corresponds to the RMS-value (Sigma). The
    Amplitude [Vp] is a floating-point number in the range between -50.000000 V and
    +50.000000 V; the decimal point must be a period (point). A negative Amplitude
    corresponds to a shift in Phase [°] of 180°. The ±50 V range in Amplitude [Vp] extends the
    flexibility in generating clipping-waveforms, also by applying a DC-Offset Voltage.
    @voltage - floating point number specifying the Vp parameter
    """
    def read_SWGAmplitude(self):
        return self.write("C SWG AMP?")

    def write_SWGAmplitude(self, voltage):
        return self.write("C SWG AMP {}".format(voltage))
    """
    Read or write the DC-Offset Voltage [V] parameter of the generated Standard Waveform.
    The DC-Offset Voltage is added to the function and therefore shifts the waveform in the
    amplitude. If "DC-Voltage only" is selected as function, this parameter is used as fixed DC-
    Voltage.
    The DC-Offset Voltage is a floating-point number in the range between -10.000000 V and
    +10.000000 V; the decimal point must be a period (point)
    @voltage - floating point number specifying the DC offset voltage
    """
    def read_SWGDCOffset(self):
        return self.write("C SWG DCV?")

    def write_SWGDCOffset(self, voltage):
        return self.write("C SWG DCV {}".format(voltage))
    """
    Read or write the Phase [°] parameter of the generated Standard Waveform. The Phase
    shifts the generated waveform in time; it isn’t applicable for Gaussian-Noise, Ramp and
    DC-Voltage only. A Sine with a Phase of 90° corresponds to a Cosine.
    The Phase [°] is a floating-point number in the range between -360.0000° and
    +360.0000°; the decimal point must be a period (point).
    @angle - floating point number indicating the phase angle
    """
    def read_SWGPhase(self):
        return self.write("C SWG PHA?")

    def write_SWGPhase(self, angle):
        return self.write("C SWG PHA {}".format(angle))
    """
    Read or write the Duty-Cycle [%] parameter for the generation of the Pulse-Waveform.
    The Duty-Cycle is only applicable for the Pulse function. A 50% Duty-Cycle results in a
    Square Wave; the higher the Duty-Cycle [%] the longer a high-level is applied.
    The Duty-Cycle [%] is a floating-point number in the range between 0.000% and
    100.000%; the decimal point must be a period (point).
    @dc - floating point number specifying the duty cycle percent
    """
    def read_SWGDutyCycle(self):
        return self.write("C SWG DUC?")

    def write_SWGDutyCycle(self, dc):
        return self.write("C SWG DUC {}".format(dc))
    """
    Read the Wave-Memory Size of the generated Standard Waveform. This Wave-Memory
    Size will also be the AWG-Memory Size, after writing to the AWG-Memory. The Wave-
    Memory Size is an integer number in the range from 10 to 34’000 and is calculated from
    the Desired Frequency [Hz] parameters of the Standard Waveform Generation.
    At the maximum frequency of 10’000 Hz a minimum Wave-Memory Size of 10 is reached
    while the AWG Clock-Period must be 10 μsec. Each point of the Wave-Memory
    corresponds to a DAC-Voltage in a range of ±10 V
    """
    def read_SWGMemSize(self):
        return self.write("C SWG MS?")
    """
    Read the Nearest AWG-Frequency [Hz] which can be reached as close as possible to the
    Desired AWG-Frequency [Hz]; is a floating-point number in the range between 0.001 Hz
    and 10’000 Hz.
    If it must be optimized, select "Adapt AWG-CLK" (see above). Not all desired AWG-
    Frequencies can be achieved, since the AWG-Clock Period can only be adjusted with a
    resolution of 1 μsec.
    """
    def read_SWGNearestFreq(self):
        return self.write("C SWG NF?")
    """
    Read the Waveform Clipping Status of the Generated Standard Waveform (SWG). If the
    amplitude of the generated waveform exceeds the maximum voltage of ± 10 V anywhere,
    the Clipping is set (1). If the Amplitude is always within the ± 10 V range (which means
    OK), the Clipping is not reset (0).
    0=Not Clipping/1=Clipping
    """
    def read_SWGClippingStatus(self):
        return self.write("C SWG CLP?")
    """
    Read the SWG/AWG Clock-Period [μsec] (10....4E9), which was used for the Standard
    Waveform Generation (SWG). This integer number represents the AWG Clock-Period in
    μsec (1E-6 sec) and the resolution is 1 μsec. If “Keep AWG Clock-Period” is selected, the
    AWG Clock-Period of the corresponding DAC-Board is read. If “Adapt AWG Clock-Period”
    is selected, the SWG/AWG Clock-Period is adapted to meet the Desired AWG Frequency
    as close as possible.
    """
    def read_SWGClkPeriod(self):
        return self.write("C SWG CP?")
    """
    Read or write the Selected Wave-Memory (WAV-A/B/C/D) to which the Wave-Function
    will be applied. If Keep AWG Clock-Period is selected above, the AWG Clock-Period of the
    corresponding DAC-Board is read: From the Lower DAC-Board if Wave-Memory A or B is
    selected and from the Higher DAC-Board if Wave-Memory C or D is selected.
    @mem - integer specifying the WAV memory, 0/1/2/3 (A/B/C/D)
    """
    def read_SWGMemSelected(self):
        return self.write("C SWG WMEM?")

    def write_SWGMemSelected(self, mem):
        return self.write("C SWG WMEM {}".format(mem))
    """
    Read or write the Selected Wave-Function which will be applied on the generated
    Standard Waveform and the Selected Wave-Memory when “Apply to Wave-Memory Now”
    is operated.
    The following Wave-Functions are available: COPY, APPEND, SUM, MULTIPLY and
    DIVIDE. When COPY Waveform is selected, the actual Wave-Memory is overwritten. The
    other four Wave-Functions can be applied to START or to the END of Wave-Memory.
    With these Wave-Functions complex and user-specific waveforms can be created in the
    Wave-Memory. Multiple Wave-Functions can be applied on different generated Standard
    Waveforms to reach the desired user-specific waveform.
    These nine different Wave-Functions are available and are represented by the following
    integer numbers:
    0 = COPY to Wave-MEM -> Overwrite
    1 = APPEND to Wave-MEM @START
    2 = APPEND to Wave-MEM @END
    3 = SUM Wave-MEM @START
    4 = SUM Wave-MEM @END
    5 = MULTIPLY Wave-MEM @START
    6 = MULTIPLY Wave-MEM @END
    7 = DIVIDE Wave-MEM @START
    8 = DIVIDE Wave-MEM @END
    @func - integer specifying the function to perform, 0/1/2/3/4/5/6/7/8 (see above for coding scheme)
    """
    def read_SWGSelectedFunc(self):
        return self.write("C SWG WFUN?")

    def write_SWGSelectedFunc(self, func):
        return self.write("C SWG WFUN {}".format(func))
    """
    Read or write the Boolean parameter No Linearization/Linearization for actual DAC-
    Channel. When “Copy to Wave-Memory Now” is performed, the actual selected AWG DAC-
    Channel gets registered for the later linearization when the WAV-Memory is written to
    the AWG-Memory. In this case the AWG-Waveform gets also linearized after applying the
    polynomial. If No Linearization is selected the DAC-Channel is registered as a zero (0)
    which indicates that no linearization will be done when the WAV-Memory is written to
    the AWG-Memory; this slightly increases the write performance.
    These two different options (No Linearization/Linearization for actual DAC-Channel) can
    be written or readout:
    0=No Linearization/1=Linearization for actual DAC-Channel
    @mode - integer specifying linearization mode, 0/1 (no lin/lin)
    """
    def read_SWGLinearization(self):
        return self.write("C SWG LIN?")

    def write_SWGLinearization(self, mode):
        return self.write("C SWG LIN {}".format(mode))
    """
    The Selected Wave-Function gets applied to the Selected Wave-Memory (WAV-A/B/C/D).
    At this moment, the actual selected AWG DAC-Channel gets registered if “Linearization for
    actual DAC-Channel” is selected (see above). After setting this control, it gets reset
    internally.
    """
    def apply_SWGFunction(self):
        return self.write("C SWG APPLY")
    



######################################################################################

#                  WAVE CONTROL COMMANDS

######################################################################################
    """
    Read the Size of one of the five Wave-Memories (WAV-A/B/C/D/S). This Wave-Memory
    Size will also be the AWG-Memory Size, after writing to the AWG-Memory. The Wave-
    Memory Size is an integer number in the range from 0 to 34’000. A Wave-Memory Size of
    zero (0) indicates that this Wave-Memory is cleared.
    Note: For optimal performance, keep the Wave-Memory Size as small as possible and
    always clear unused Wave-Memories.
    @mem - character indicating the wave memory, A/B/C/D/S 
    """
    def read_WAVMemSize(self, mem):
        return self.write("C WAV-{} MS?".format(mem))
    """
    Clear the selected Wave-Memory (WAV-A/B/C/D/S) and set the Wave-Memory Size to
    zero (0). The WAV-S is the Saved Waveform. After setting this control, it gets reset
    internally
    @mem - character indicating the wave memory, A/B/C/D/S 
    """
    def clear_WAVMem(self, mem):
        return self.write("C WAV-{} CLR".format(mem))
    """
    Save the selected Wave-Memory (WAV-A/B/C/D) to the internal volatile memory on the
    LNHR DAC II; it is called WAV-S.
    @mem - character indicating the wave memory, A/B/C/D/S 
    """
    def save_WAVMem(self, mem):
        return self.write("C WAV-{} SAVE".format(mem))
    """
    Read the corresponding DAC-Channel for the Linearization of one of the four Wave-
    Memories (WAV-A/B/C/D). The Linearization for this DAC-Channel is done when the
    Wave-Memory is written to the AWG-Memory. If "No Linearization" was selected when
    the waveform was copied to the Wave-Memory, the corresponding DAC-Channel is 0
    (zero). The DAC-Channel for Linearization is an integer number in the range from 0 to 24;
    the not existing DAC-Channel 0 (zero) means that no linearization gets applied.
    @mem - character indicating the wave memory, A/B/C/D/S 
    """
    def read_WAVMemLinChannel(self, mem):
        return self.write("C WAV-{} LINCH?".format(mem))
    """
    Write the Wave-Memory (WAV-A/B/C/D) to the corresponding AWG-Memory (AWG-
    A/B/C/D). After setting this control, it gets reset internally. The Polynomial is only applied
    when the corresponding Boolean parameter "Apply Polynomial" is selected (see chapter
    “2D-Scan CONTROL Commands”).
    Note: The Saved Waveform (WAV-S) has first to be copied to one of the four Wave-
    Memories (WAV-A/B/C/D) before it can be written to the corresponding AWG-Memory.
    To recalled the Saved Waveform (WAV-S) select “Use Saved Waveform” in the SWG Mode
    selection
    @mem - character indicating the wave memory, A/B/C/D/S 
    """
    def write_WAVMemToAWGMem(self, mem):
        return self.write("C WAV-{} WRITE".format(mem))
    """
    During writing the Wave-Memory (WAV-A/B/C/D) to the corresponding AWG-Memory
    (AWG-A/B/C/D) this Busy flag is set (1); if it is Idle state the value is zero (0).
    0=Idle/1=Busy (writing WAV- to AWG-Memory
    @mem - character indicating the wave memory, A/B/C/D/S 
    """
    def read_WAVBusyWriting(self, mem):
        return self.write("C WAV-{} BUSY?".format(mem))


####################################################################

#               SPECIAL AND COMPOUND FUNCTIONS

####################################################################

    """
    Creates a linear scan of the given parameter (for example a DAC channel), from a START value
    to a STOP value, with num_points pauses/measurements. A time delay is made before a measured 
    dependent parameter is read and stored into a list.  The list is returned after the scan.
    @param - the independent parameter.  Must have a set() method
    @start - the starting value for the scan
    @stop - the stopping value for the scan
    @num_points - the number of points within the scan.
    @delay - the time to pause at each point before reading any dependent parameters.
    @measured_param - the dependent parameter to measure.  Must have a get() method.
    """
    def scan1D(self, param, start, stop, num_points, delay, measured_param):
        data = [] 
        increment = (stop - start) / (num_points-1)
        current = start
        
        values = []
        for i in range(num_points - 1):
            values.append(current)
            current += increment
        values.append(stop)
        for val in values:
            param.set(val)
            time.sleep(delay)
            m = measured_param.get()
            print(m)
            data.append(m)
        return data


    """
    Creates a 2D linear scan of two independent parameters.  The "outer-loop" parameter is param1, and runs through it's
    scan only once. The "inner-loop" parameter, param2, runs through a scan each time param1 steps. At each step, 
    the dependent parameters, stored in a list, are read and recorded.
    @param1 - the independent outer-loop parameter.  Must have a set() method
    @start1 - the starting value for the outer scan
    @stop1 - the stopping value for the outer scan
    @num_points1 - the number of points within the outer scan.
    @delay1 - the time to pause at each point of the outer scan before reading any dependent parameters.
    @param2 - the independent inner-loop parameter.  Must have a set() method
    @start2 - the starting value for the inner scan
    @stop2 - the stopping value for the inner scan
    @num_points2 - the number of points within the inner scan.
    @delay2 - the time to pause at each point of the inner scan before reading any dependent parameters.
    @measured_params_list - a list of dependent parameters. Each must have a get() method
    """
    def scan2D(self, param1, start1, stop1, num_points1, delay1, param2, start2, stop2, num_points2, delay2, measured_params_list):
        data = [] # return variable
        increment1 = (stop1 - start1) / (num_points1 - 1)
        increment2 = (stop2 - start2) / (num_points2 - 1)

        current1 = start1
        current2 = start2
        values1 = []
        values2 = []
        for i in range(num_points1 - 1):
            values1.append(current1)
            current1 += increment1
        values1.append(stop1)
        for i in range(num_points2 - 1):
            values2.append(current2)
            current2 += increment2
        values2.append(stop2)
        
        for val1 in values1:
            param1.set(val1)
            time.sleep(delay1)
            line_data = []
            for val2 in values2:
                param2.set(val2)
                time.sleep(delay2)
                data_point = []
                for p in measured_params_list:
                    data_point.append(p.get())
                line_data.append(tuple(data_point))
            # append data list for scan line into return variable
            data.append(line_data)
        return data

    def handleDACSetErrors(code):
        num = int(code)
        if num == 0:
            return num
        elif num == 1:
            print("Invalid DAC-Channel")
        elif num == 2:
            print("Missing DAC-Value, Status or BW")
        elif num == 3:
            print("DAC-Value out of range")
        elif num == 4:
            print("Mistyped")
        elif num == 5:
            print("Writing not allowed (Ramp/Step-Generator or AWG are running on this DAC-Channel)")
        return num

    def handleAWGSetErrors(code):
        num = int(code)
        if num == 0:
            return num
        if num == 1:
            print("Invalid AWG-Memory")
        elif num == 2:
            print("Missing AWG-Address and/or AWG-Value")
        elif num == 3:
            print("AWG-Address and/or AWG-Value out of range")
        elif num == 4:
            print("Mistyped")
        return num

    def handleWAVSetErrors(code):
        num = int(code)
        if num == 0:
            return num
        if num == 1:
            print("Invalid WAV-Memory")
        elif num == 2:
            print("Missing WAV-Address and/or WAV-Voltage")
        elif num == 3:
            print("WAV-Address and/or WAV-Voltage out of range")
        elif num == 4:
            print("Mistyped")
        return num

    def handlePOLYSetErors(code):
        num = int(code)
        if num == 0:
            return num
        if num == 1:
            print("Invalid Polynomial Name")
        elif num == 2:
            print("Missing Polynomial Coefficient(s)")
        elif num == 4:
            print("Mistyped")
        return num
    
    """
    After each CONTROL Write command, an error code will be returned.  '0' indicates no error. 
    If you want an interpretation printed to standard output, pass the code into this method.
    Additional actions should be taken in the code surrounding the write function.
    You should at least check for '0', to know that your program can continue running normally.
    """
    def handleCONTROLWriteErrors(code):
        num = int(code)
        if num == 0:
            return num
        if num == 1:
            print("Invalid DAC-Channel")
        elif num == 2:
            print("Invalid Parameter")
        elif num == 4:
            print("Mistyped")
        elif num == 5:
            print("Writing not allowed")

