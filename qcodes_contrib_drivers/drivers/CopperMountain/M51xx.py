from typing import Sequence, Union, Any
import time
import re
import logging

import numpy as np
from pyvisa import VisaIOError, errors
from qcodes import (VisaInstrument, InstrumentChannel, ArrayParameter,
                    ChannelList, Parameter)
from qcodes.utils.validators import Ints, Numbers, Enum, Bool

logger = logging.getLogger()

class CMTSweep(ArrayParameter):
    def __init__(self,
                 name: str,
                 instrument: 'CMTBase',
                 **kwargs: Any) -> None:

        super().__init__(name,
                         instrument=instrument,
                         shape=(0,),
                         setpoints=((0,),),
                         **kwargs)

    @property  # type: ignore[override]
    def shape(self) -> Sequence[int]:  # type: ignore[override]
        if self._instrument is None:
            return (0,)
        return (self._instrument.root_instrument.points(),)
    @shape.setter
    def shape(self, val: Sequence[int]) -> None:
        pass

    @property  # type: ignore[override]
    def setpoints(self) -> Sequence:  # type: ignore[override]
        if self._instrument is None:
            raise RuntimeError("Cannot return setpoints if not attached "
                               "to instrument")
        # if its in zero span, return duration of sweep

        vna = self._instrument.root_instrument
        if vna.span() == 0 :
            raise ValueError( 'In zero span mode. use magnitude_time or phase_time parameters' )
        start = vna.start()
        stop = vna.stop()
        return (np.linspace(start, stop, self.shape[0]),)
    @setpoints.setter
    def setpoints(self, val: Sequence[int]) -> None:
        pass

class FormattedSweep(CMTSweep):
    """
    Mag will run a sweep, including averaging, before returning data.
    As such, wait time in a loop is not needed.
    """
    def __init__(self,
                 name: str,
                 instrument: 'CMTBase',
                 sweep_format: str,
                 label: str,
                 unit: str,
                 memory: bool = False) -> None:
        super().__init__(name,
                         instrument=instrument,
                         label=label,
                         unit=unit,
                         setpoint_names=('frequency',),
                         setpoint_labels=('$f_{\mathrm{VNA}}$',),
                         setpoint_units=('Hz',)
                         )
        self.sweep_format = sweep_format
        self.memory = memory

    def get_raw(self) -> Sequence[float]:
        if self._instrument is None:
            raise RuntimeError("Cannot get data without instrument")

        # Check if we should run a new sweep
        
        self.instrument.format( self.sweep_format )
        self.instrument.write('TRIG:SEQ:SING') #Trigger a single sweep
        self.instrument.write('TRIG:WAIT ENDM') #Trigger a single sweep
        self.instrument.ask('*OPC?') #Wait for measurement to complete

        cmd = f"CALC:DATA:FDAT?"
        S11 = self.instrument.ask(cmd) #Get data as string


        #Chage the string values into numbers
        S11 = [float(s) for s in S11.split(',')]

        return np.array( S11[::2] )

class TimeSweep(FormattedSweep):
    """ Set special sweeper for time.
    Has different x units and get setpoints differently
    """
    def __init__(self,
                 name: str,
                 instrument: 'CMTBase',
                 sweep_format: str,
                 label: str,
                 unit: str,
                 memory: bool = False) -> None:
        CMTSweep.__init__( self, name,
                         instrument=instrument,
                         label=label,
                         unit=unit,
                         setpoint_names=('time',),
                         setpoint_labels=('$t_{\\mathrm{VNA}}$',),
                         setpoint_units=('s',)
                         )
        self.sweep_format = sweep_format
        self.memory = memory

    @property  # type: ignore[override]
    def setpoints(self) -> Sequence:  # type: ignore[override]
        if self._instrument is None:
            raise RuntimeError("Cannot return setpoints if not attached "
                               "to instrument")
        # if its in zero span, return duration of sweep

        vna = self._instrument.root_instrument
        if vna.span() != 0 :
            raise ValueError( 'Not in zero span mode. Set span to zero and place marker at end of time trace to continue.' )
        
        start = 0
        stop = vna.marker_x()
        return (np.linspace(start, stop, self.shape[0]),)

    @setpoints.setter
    def setpoints(self, val: Sequence[int]) -> None:
        pass

    # @property  # type: ignore[override]
    # def setpoints(self) -> Sequence:  # type: ignore[override]
    #     if self._instrument is None:
    #         raise RuntimeError("Cannot return setpoints if not attached "
    #                            "to instrument")
    #     # if its in zero span, return duration of sweep
    #     vna = self._instrument.root_instrument
    #     if vna.span() == 0.0 :
    #         start = 0
    #         stop = vna.marker_x() # HACK: place the marker at the end of the trace
    #     else :
    #         raise ValueError( 'span is not 0. Set it to zero and place marker at the end of the trace.' )
        
    #     return (np.linspace(start, stop, self.shape[0]),)

class CMTPort(InstrumentChannel):
    """
    Allow operations on individual CMT ports.
    Note: This can be expanded to include a large number of extra parameters...
    """

    def __init__(self,
                 parent: 'CMTBase',
                 name: str,
                 port: int,
                 min_power: Union[int, float],
                 max_power: Union[int, float]) -> None:
        super().__init__(parent, name)

        self.port = int(port)
        if self.port < 1 or self.port > 1:
            raise ValueError("Port must be 1.")

        pow_cmd = f"SOUR{self.port}:POW"
        self.add_parameter("source_power",
                           label="$P_{\mathrm{VNA}}$",
                           unit="dBm",
                           get_cmd=f"{pow_cmd}?",
                           set_cmd=f"{pow_cmd} {{}}",
                           get_parser=float,
                           vals=Numbers(min_value=min_power,
                                        max_value=max_power))

    def _set_power_limits(self,
                          min_power: Union[int, float],
                          max_power: Union[int, float]) -> None:
        """
        Set port power limits
        """
        self.source_power.vals = Numbers(min_value=min_power,
                                         max_value=max_power)

class CMTTrace(InstrumentChannel):
    """
    Allow operations on individual CMT traces.
    """

    def __init__(self,
                 parent: 'CMTBase',
                 name: str,
                 trace_name: str,
                 trace_num: int) -> None:
        super().__init__(parent, name)
        self.trace_name = trace_name
        self.trace_num = trace_num

        # Name of parameter (i.e. S11, S21 ...)
        self.add_parameter('trace',
                           label='Trace',
                           get_cmd=self._Sparam,
                           set_cmd=self._set_Sparam)
        # Format
        # Note: Currently parameters that return complex values are not
        # supported as there isn't really a good way of saving them into the
        # dataset
        self.add_parameter('format',
                           label='Format',
                           get_cmd='CALC:FORM?',
                           set_cmd='CALC:FORM {}',
                           vals=Enum('MLIN', 'MLOG', 'PHAS',
                                     'UPH', 'IMAG', 'REAL'))

        # And a list of individual formats
        self.add_parameter('phase_time',
                           sweep_format='UPH',
                           label='$\phi_{\mathrm{VNA}}$',
                           unit='deg',
                           parameter_class=TimeSweep )
        self.add_parameter('magnitude_time',
                           sweep_format='MLOG',
                           label='$|S_{21}|$',
                           unit='dB',
                           parameter_class=TimeSweep)  

        self.add_parameter('magnitude',
                           sweep_format='MLOG',
                           label='$|S_{21}|$',
                           unit='dB',
                           parameter_class=FormattedSweep)
        self.add_parameter('linear_magnitude',
                           sweep_format='MLIN',
                           label='Magnitude',
                           unit='ratio',
                           parameter_class=FormattedSweep)
        self.add_parameter('phase',
                           sweep_format='PHAS',
                           label='$\phi_{\mathrm{VNA}}$',
                           unit='deg',
                           parameter_class=FormattedSweep)
        self.add_parameter('unwrapped_phase',
                           sweep_format='UPH',
                           label='Phase',
                           unit='deg',
                           parameter_class=FormattedSweep)
        self.add_parameter("group_delay",
                           sweep_format='GDEL',
                           label='Group Delay',
                           unit='s',
                           parameter_class=FormattedSweep)
        self.add_parameter('electrical_delay',
                           label='Electrical Delay',
                           get_cmd='CALC:TRAC' + str( trace_num ) + ':CORR:EDEL:TIME?',
                           get_parser=float,
                           set_cmd='CALC:TRAC' + str( trace_num ) + ':CORR:EDEL:TIME {:.6e}',
                           unit='s',
                           vals=Numbers(min_value=0, max_value=100000))
        
        # Marker
        self.add_parameter('marker_y',
                           label='$\mathrm{S}_{21}$',
                           get_cmd=self._marker_tr,
                           get_parser=float,
                           set_cmd='CALC1:TRAC1:MARK:Y {}',
                           unit='dB')
        self.add_parameter('marker_x',
                           label='$f_{\mathrm{marker}}$',
                           get_cmd='CALC1:MARK:X?',
                           get_parser=float,
                           set_cmd='CALC1:MARK:X {}',
                           unit='Hz')
        
        self.add_parameter('marker_phase',
                           label='$\phi_{\mathrm{marker}}$',
                           get_cmd=self._marker_ph,
                           get_parser=float,
                           set_cmd='CALC1:TRAC2:MARK:X {}',
                           unit='Degrees')

        self.add_parameter('marker_Q',
                           label='$Q$',
                           get_cmd=self._marker_Q,
                           get_parser=float,
                           unit='')

        self.add_parameter('real',
                           sweep_format='REAL',
                           label='Real',
                           unit='LinMag',
                           parameter_class=FormattedSweep)
        self.add_parameter('imaginary',
                           sweep_format='IMAG',
                           label='Imaginary',
                           unit='LinMag',
                           parameter_class=FormattedSweep)

    def run_sweep(self) -> str:
        """
        Run a set of sweeps on the network analyzer.
        Note that this will run all traces on the current channel.
        """
        root_instr = self.root_instrument
        self.write('TRIG:SING')
        self.ask('*OPC?\n') #Wait for measurement to complete

        # # Once the sweep mode is in hold, we know we're done
        # try:
        #     while root_instr.sweep_mode() != 'HOLD':
        #         time.sleep(0.1)
        # except KeyboardInterrupt:
        #     # If the user aborts because (s)he is stuck in the infinite loop
        #     # mentioned above, provide a hint of what can be wrong.
        #     msg = "User abort detected. "
        #     source = root_instr.trigger_source()
        #     if source == "MAN":
        #         msg += "The trigger source is manual. Are you sure this is " \
        #                "correct? Please set the correct source with the " \
        #                "'trigger_source' parameter"
        #     elif source == "EXT":
        #         msg += "The trigger source is external. Is the trigger " \
        #                "source functional?"
        #     logger.warning(msg)

        # Return previous mode, incase we want to restore this
        # return prev_mode
        
    def write(self, cmd: str) -> None:
        """
        Select correct trace before querying
        """
        self.root_instrument.active_trace(self.trace_num)
        super().write(cmd)

    def ask(self, cmd: str) -> str:
        """
        Select correct trace before querying
        """
        self.root_instrument.active_trace(self.trace_num)
        return super().ask(cmd)

    def _Sparam(self) -> str:
        """
        Extrace S_parameter from returned CMT format
        """
        paramspec = self.root_instrument.get_trace_catalog()
        specs = paramspec.split(',')
        for spec_ind in range(len(specs)//2):
            name, param = specs[spec_ind*2:(spec_ind+1)*2]
            if name == self.trace_name:
                return param
        raise RuntimeError("Can't find selected trace on the CMT")

    def _marker_tr(self) -> str:
        """
        Get magnitude of marker 1
        """
        self.root_instrument.ask('*OPC?\n')
        return self.root_instrument.ask('CALC1:TRAC1:MARK:Y?').split(',')[0]

    def _marker_ph(self) -> str:
        """
        Get phase of marker 1
        """
        self.root_instrument.ask('*OPC?\n')
        return self.root_instrument.ask('CALC1:TRAC2:MARK:Y?').split(',')[0]

    def _marker_Q(self) -> str:
        """
        Get Q of marker 1
        """
        self.root_instrument.ask('*OPC?\n')
        return self.root_instrument.ask('CALC1:TRAC1:MARK:BWID:DATA?').split(',')[2]

    def _set_Sparam(self, val: str) -> None:
        """
        Set an S-parameter, in the format S<a><b>, where a and b
        can range from 1-4
        """
        if not re.match("S[1-4][1-4]", val):
            raise ValueError("Invalid S parameter spec")
        self.write(f"CALC:PAR:SEL \"{val}\"")

class CMTBase(VisaInstrument):
    """
    Base qcodes driver for CMT Network Analyzers

    """

    def __init__(self,
                 name: str,
                 address: str,
                 # Set frequency ranges
                 min_freq: Union[int, float], max_freq: Union[int, float],
                 # Set power ranges
                 min_power: Union[int, float], max_power: Union[int, float],
                 nports: int, # Number of ports on the CMT
                 **kwargs: Any) -> None:
        super().__init__(name, address, terminator='\n', **kwargs)
        self.min_freq = min_freq
        self.max_freq = max_freq
        # set the active trace to 1 since we can't figure out how to read it out
        self.select_trace_by_name( "tr1" )

        #Ports
        ports = ChannelList(self, "CMTPorts", CMTPort)
        for port_num in range(1, nports+1):
            port = CMTPort(self, f"port{port_num}", port_num,
                           min_power, max_power)
            ports.append(port)
            self.add_submodule(f"port{port_num}", port)
        ports.lock()
        self.add_submodule("ports", ports)

        # Drive power
        self.add_parameter('power',
                           label='$P_{\mathrm{VNA}}$',
                           get_cmd='SOUR:POW?',
                           get_parser=float,
                           set_cmd='SOUR:POW {:.2f}',
                           unit='dBm',
                           vals=Numbers(min_value=min_power,
                                        max_value=max_power))

        # IF bandwidth
        self.add_parameter('if_bandwidth',
                           label='IF Bandwidth',
                           get_cmd='SENS:BAND?',
                           get_parser=float,
                           set_cmd='SENS:BAND {:.2f}',
                           unit='Hz',
                           vals=Numbers(min_value=1, max_value=15e6))

        # Number of averages (also resets averages)
        self.add_parameter('averages_enabled',
                           label='Averages Enabled',
                           get_cmd="SENS:AVER?",
                           set_cmd="SENS:AVER {}",
                           val_mapping={True: '1', False: '0'})
                           
        self.add_parameter('averages',
                           label='Averages',
                           get_cmd='SENS:AVER:COUN?',
                           get_parser=int,
                           set_cmd='SENS:AVER:COUN {:d}',
                           unit='',
                           vals=Numbers(min_value=1, max_value=65536))

        # RF OUT -> Turns the VNA ON/OFF

        self.add_parameter('rf_out',
                           label='RF Out',
                           get_cmd="OUTP:STAT?",
                           set_cmd="OUTP:STAT {}",
                           val_mapping={True: '1', False: '0'})

        # Setting frequency range
        self.add_parameter('start',
                           label='Start Frequency',
                           get_cmd='SENS:FREQ:STAR?',
                           get_parser=float,
                           set_cmd='SENS:FREQ:STAR {}',
                           unit='Hz',
                           vals=Numbers(min_value=min_freq,
                                        max_value=max_freq))
        self.add_parameter('stop',
                           label='Stop Frequency',
                           get_cmd='SENS:FREQ:STOP?',
                           get_parser=float,
                           set_cmd='SENS:FREQ:STOP {}',
                           unit='Hz',
                           vals=Numbers(min_value=min_freq,
                                        max_value=max_freq))
        self.add_parameter('center',
                           label='Center Frequency',
                           get_cmd='SENS:FREQ:CENT?',
                           get_parser=float,
                           set_cmd='SENS:FREQ:CENT {}',
                           unit='Hz',
                           vals=Numbers(min_value=min_freq,
                                        max_value=max_freq))
        self.add_parameter('span',
                           label='Frequency Span',
                           get_cmd='SENS:FREQ:SPAN?',
                           get_parser=float,
                           set_cmd='SENS:FREQ:SPAN {}',
                           unit='Hz',
                           vals=Numbers(min_value=0,
                                        max_value=max_freq))

        # Number of points in a sweep
        self.add_parameter('points',
                           label='Points',
                           get_cmd='SENS:SWE:POIN?',
                           get_parser=int,
                           set_cmd='SENS:SWE:POIN {}',
                           unit='',
                           vals=Numbers(min_value=1, max_value=100001))

        # Electrical delay
        self.add_parameter('electrical_delay',
                           label='Electrical Delay',
                           get_cmd='CALC:CORR:EDEL:TIME?',
                           get_parser=float,
                           set_cmd='CALC:CORR:EDEL:TIME {:.6e}',
                           unit='s',
                           vals=Numbers(min_value=0, max_value=100000))


        # Sweep Time
        # SYST:CYCL:TIME:MEAS?
        self.add_parameter('sweep_time',
                           label='Time',
                           get_cmd='SYST:CYCL:TIME:MEAS?',
                           get_parser=float,
                           unit='s',
                           vals=Numbers(0, 1e6))
        # Sweep Mode
        self.add_parameter('sweep_mode',
                           label='Mode',
                           get_cmd='INIT:CONT?',
                           set_cmd='INIT:CONT {}',
                           vals=Ints( 0, 1 ))
        # Number of traces in the channel
        # TODO: this shoudl probably be moved to port
        self.add_parameter('trace_count',
                           get_cmd="CALC:PAR:COUN?",
                           get_parser=int,
                           set_cmd="SENS:PAR:COUN {}",
                           vals=Ints(1, 2000000))
        # Trigger Source
        self.add_parameter('trigger_source',
                           get_cmd="TRIG:SOUR?",
                           set_cmd="TRIG:SOUR {}",
                           vals=Enum("EXT", "IMM", "MAN"))

        # Traces
        self.add_parameter('active_trace',
                           label='Active Trace',
                           get_parser=int,
                           set_cmd="CALC:PAR{}:SEL",
                           vals=Numbers(min_value=1, max_value=24))
        self.active_trace.get = lambda : self._active_trace
        # Note: Traces will be accessed through the traces property which
        # updates the channellist to include only active trace numbers
        self._traces = ChannelList(self, "CMTTraces", CMTTrace)
        self.add_submodule("traces", self._traces)
        # Add shortcuts to first trace
        trace1 = self.traces[0]
        params = trace1.parameters
        if not isinstance(params, dict):
            raise RuntimeError(f"Expected trace.parameters to be a dict got "
                               f"{type(params)}")
        for param in params.values():
            self.parameters[param.name] = param
        # And also add a link to run sweep
        self.run_sweep = trace1.run_sweep
        # Set this trace to be the default (it's possible to end up in a
        # situation where no traces are selected, causing parameter snapshots
        # to fail)
        self.active_trace(trace1.trace_num)

        # Set auto_sweep parameter
        # If we want to return multiple traces per setpoint without sweeping
        # multiple times, we should set this to false
        self.add_parameter('auto_sweep',
                           label='Auto Sweep',
                           set_cmd=None,
                           get_cmd=None,
                           vals=Bool(),
                           initial_value=True)

        # A default output format on initialisation
        self.write('FORM REAL,32')
        self.write('FORM:BORD NORM')

        self.connect_message()

    @property
    def traces(self) -> ChannelList:
        """
        Update channel list with active traces and return the new list
        """
        # Keep track of which trace was active before. This command may fail
        # if no traces were selected.
        try:
            active_trace = self.active_trace()
        except VisaIOError as e:
            if e.error_code == errors.StatusCode.error_timeout:
                active_trace = None
            else:
                raise

        # Get a list of traces from the instrument and fill in the traces list
        parlist = self.get_trace_catalog().split(",")
        self._traces.clear()
        for trace_name in parlist[::2]:
            trace_num = self.select_trace_by_name(trace_name)
            CMT_trace = CMTTrace(self, "tr{}".format(trace_num),
                                 trace_name, trace_num)
            self._traces.append(CMT_trace)

        # Restore the active trace if there was one
        if active_trace:
            self.active_trace(active_trace)

        # Return the list of traces on the instrument
        return self._traces

    def get_options(self) -> Sequence[str]:
        # Query the instrument for what options are installed
        return self.ask('*OPT?').strip('"').split(',')

    def get_trace_catalog(self):
        """
        Get the trace catalog, that is a list of trace and sweep types
        from the CMT.

        The format of the returned trace is:
            trace_name,trace_type,trace_name,trace_type...
        we will use
        tr1_sxx,sxx,tr2_sxx_sxx,...
        """
        catalog = ""
        for n in range( self.trace_count() ):
            query = f"CALC:PAR{n+1}:DEF?"
            s = self.ask(query).strip('"')
            catalog += f"tr{n+1}_{s},{s},"
        return catalog[:-1]

    def select_trace_by_name(self, trace_name: str) -> int:
        """
        Select a trace on the CMT by name.

        Returns:
            The trace number of the selected trace
        """
        tr_num = int( trace_name[2] )
        self.write(f"CALC:PAR{tr_num}:SEL")
        self._active_trace = tr_num
        return tr_num

    def reset_averages(self):
        """
        Reset averaging
        """
        self.write("SENS:AVER:CLE")

    def averages_on(self):
        """
        Turn on trace averaging
        """
        self.averages_enabled(True)

    def averages_off(self):
        """
        Turn off trace averaging
        """
        self.averages_enabled(False)

    def _set_power_limits(self,
                          min_power: Union[int, float],
                          max_power: Union[int, float]) -> None:
        """
        Set port power limits
        """
        self.power.vals = Numbers(min_value=min_power,
                                  max_value=max_power)
        for port in self.ports:
            port._set_power_limits(min_power, max_power)

class CMTxBase(CMTBase):
    def _enable_fom(self) -> None:
        '''
        CMT-x units with two sources have an enormous list of functions &
        configurations. In practice, most of this will be set up manually on
        the unit, with power and frequency varied in a sweep.
        '''
        self.add_parameter('aux_frequency',
                           label='Aux Frequency',
                           get_cmd='SENS:FOM:RANG4:FREQ:CW?',
                           get_parser=float,
                           set_cmd='SENS:FOM:RANG4:FREQ:CW {:.2f}',
                           unit='Hz',
                           vals=Numbers(min_value=self.min_freq,
                                        max_value=self.max_freq))

