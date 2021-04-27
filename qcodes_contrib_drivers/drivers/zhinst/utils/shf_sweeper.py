"""Class for frequency sweeps on SHFQA
"""

# Copyright 2020 Zurich Instruments AG

from collections import namedtuple
from dataclasses import dataclass
from enum import Enum
import time
import numpy as np


class _Mapping(Enum):
    LIN = "linear"
    LOG = "log"


class _AveragingMode(Enum):
    SWEEPWISE = "sweepwise"
    POINTWISE = "pointwise"


class _TriggerSource(Enum):
    TRIGGERIN_1_A = "channel0_trigger_input0"
    TRIGGERIN_1_B = "channel0_trigger_input1"
    TRIGGERIN_2_A = "channel1_trigger_input0"
    TRIGGERIN_2_B = "channel1_trigger_input1"
    TRIGGERIN_3_A = "channel2_trigger_input0"
    TRIGGERIN_3_B = "channel2_trigger_input1"
    TRIGGERIN_4_A = "channel3_trigger_input0"
    TRIGGERIN_4_B = "channel3_trigger_input1"
    SEQTRIGGER_1 = "channel0_sequencer_trigger0"
    SEQTRIGGER_2 = "channel1_sequencer_trigger0"
    SEQTRIGGER_3 = "channel2_sequencer_trigger0"
    SEQTRIGGER_4 = "channel3_sequencer_trigger0"
    SWTRIGGER = "sw_trigger"


_TRIGGER_MAPPING = {
    _TriggerSource.TRIGGERIN_1_A: 0,
    _TriggerSource.TRIGGERIN_1_B: 1,
    _TriggerSource.TRIGGERIN_2_A: 2,
    _TriggerSource.TRIGGERIN_2_B: 3,
    _TriggerSource.TRIGGERIN_3_A: 4,
    _TriggerSource.TRIGGERIN_3_B: 5,
    _TriggerSource.TRIGGERIN_4_A: 6,
    _TriggerSource.TRIGGERIN_4_B: 7,  # HW Trigger limit
    _TriggerSource.SEQTRIGGER_1: 32,
    _TriggerSource.SEQTRIGGER_2: 33,
    _TriggerSource.SEQTRIGGER_3: 34,
    _TriggerSource.SEQTRIGGER_4: 35,
    _TriggerSource.SWTRIGGER: 1024,
}

_HW_TRIGGER_LIMIT = 8


def _check_trigger_source(trigger):
    try:
        _TriggerSource(trigger.lower())
    except ValueError:
        print(
            (
                "Trigger source needs to be 'channel[0,3]_trigger_input[0,1]', "
                "'channel[0,3]_sequencer_trigger0' or 'sw_trigger'."
            )
        )


def _check_center_freq(center_freq_hz):
    min_center_freq = 0
    max_center_freq = 8e9
    center_freq_steps = 100e6
    rounding_error = 0.1

    if center_freq_hz < min_center_freq:
        raise ValueError(f"Center frequency must be greater than {min_center_freq}Hz.")
    if center_freq_hz > max_center_freq:
        raise ValueError(f"Center frequency must be less than {max_center_freq}Hz.")
    if center_freq_hz % center_freq_steps > rounding_error:
        raise ValueError(f"Center frequency must be multiple of {center_freq_steps}Hz.")


def _check_in_band_freq(start_freq, stop_freq):
    min_offset_freq = -1e9
    max_offset_freq = 1e9

    if start_freq >= stop_freq:
        raise ValueError("Stop frequency must be larger than start_freq frequency.")
    if start_freq < min_offset_freq:
        raise ValueError(f"Start frequency must be greater than {min_offset_freq}Hz.")
    if stop_freq > max_offset_freq:
        raise ValueError(f"Stop frequency must be less than {max_offset_freq}Hz.")


def _check_io_range(range_dbm):
    max_range = 10
    min_range = -30
    range_step = 5
    rounding_error = 0.001
    if range_dbm > max_range + rounding_error:
        raise ValueError(f"Maximum range is {max_range}dBm.")
    if range_dbm < min_range - rounding_error:
        raise ValueError(f"Minimum range is {min_range}dBm.")
    if range_dbm % range_step > rounding_error:
        raise ValueError(f"Range must be multiple of {range_step}dBm.")


def _check_output_gain(gain):
    max_gain = 1
    min_gain = 0.01
    if gain < min_gain or gain > max_gain:
        raise ValueError(f"Output gain must be within [{min_gain}, {max_gain}].")


def _check_mapping(mapping):
    try:
        _Mapping(mapping.lower())
    except ValueError:
        print("Mapping needs to be 'linear' or 'log'.")


def _check_avg_mode(mode):
    try:
        _AveragingMode(mode.lower())
    except ValueError:
        print("Averaging mode needs to be 'sweepwise' or 'pointwise'.")


def _print_sweep_progress(freq):
    hide_last_line_spaces = " " * 5
    print(f"Sweep at {(freq / 1e6):.2f}MHz.{hide_last_line_spaces}", end="\r")


@dataclass
class SweepConfig:
    """Frequency range settings for a sweep"""

    start_freq: float = -300e6
    stop_freq: float = 300e6
    num_points: int = 100
    mapping: str = "linear"
    oscillator_gain: float = 1


@dataclass
class RfConfig:
    """RF in- and ouput settings for a sweep"""

    channel: int = 0
    input_range: int = -5
    output_range: int = 0
    center_freq: float = 5e9


@dataclass
class AvgConfig:
    """Averaging settings for a sweep"""

    dwell_time: float = 1e-3
    num_samples: int = 1
    mode: str = "sweepwise"


@dataclass
class TriggerConfig:
    """Settings for the trigger"""

    source: str = "sw_trigger"
    level: float = 0.5
    imp50: bool = True


Config = namedtuple("Config", ["sweep", "avg", "rf", "trig"])

# pylint: disable=too-many-instance-attributes
class ShfSweeper:
    """
    Class to set up and run a sweep on an SHFQA

    Arguments:
        daq (zhinst.ziPython.ziDAQServer):
            ziDAQServer object to communicate with a Zurich Instruments data server
        dev (str):
            The ID of the device to run the sweeper with. For example, `dev12004`.
    """

    _sweep = SweepConfig()
    _rf = RfConfig()
    _avg = AvgConfig()
    _trig = TriggerConfig()

    _shf_sample_rate = 2e9
    _path_prefix = ""
    _result = []

    def __init__(self, daq, dev):
        self._daq = daq
        self._dev = dev
        self._set_path_prefix()

    def run(self):
        """
        Perform a sweep with the specified settings.
        Returns a dictionary with measurement data of the sweep
        """
        self._init_sweep()
        if self._trig.source.lower() == _TriggerSource.SWTRIGGER.value:
            self._run_freq_sweep()
        else:
            self._run_freq_sweep_trig()
        return self.get_result()

    def get_result(self):
        """
        Returns a dictionary with measurement data of the last sweep
        """
        data = self._get_result_logger_data()
        vec = self._result
        vec = self._average_samples(vec)
        data["vector"] = vec
        props = data["properties"]
        props["centerfreq"] = self._rf.center_freq
        props["startfreq"] = self._sweep.start_freq
        props["stopfreq"] = self._sweep.stop_freq
        props["numpoints"] = self._sweep.num_points
        props["mapping"] = self._sweep.mapping
        return data

    def plot(self):
        """
        Plots power over frequency for last sweep
        """
        import matplotlib.pyplot as plt

        freq = self.get_offset_freq_vector()
        freq_mhz = freq / 1e6
        data = self.get_result()
        input_res = 50
        power = np.abs(data["vector"]) ** 2 / input_res
        phase = np.unwrap(np.angle(data["vector"]))
        fig, axs = plt.subplots(2, sharex=True)
        plt.xlabel("freq [MHz]")

        axs[0].plot(freq_mhz, 10 * np.log10(power * 1e3))
        axs[0].set(ylabel="power [dBm]")
        axs[0].grid()

        axs[1].plot(freq_mhz, phase)
        axs[1].set(ylabel="phase [rad]")
        axs[1].grid()

        fig.suptitle(f"Sweep with center frequency {self._rf.center_freq / 1e9}GHz")
        plt.show()

    def set_to_device(self):
        """
        Transfer settings to device
        """
        self._set_rf_paths()
        self._set_trigger()
        self._daq.sync()

    def configure(
        self, sweep_config=None, avg_config=None, rf_config=None, trig_config=None
    ):
        """
        Configure and check the settings
        sweep_config: SweepConfig
        avg_config: AvgConfig
        rf_config: RfConfig
        trig_config: TriggerConfig
        """
        if rf_config:
            _check_center_freq(rf_config.center_freq)
            _check_io_range(rf_config.input_range)
            _check_io_range(rf_config.output_range)
        if sweep_config:
            _check_in_band_freq(sweep_config.start_freq, sweep_config.stop_freq)
            _check_mapping(sweep_config.mapping)
            _check_output_gain(sweep_config.oscillator_gain)
        if avg_config:
            _check_avg_mode(avg_config.mode)
            self._check_dwell_time(avg_config.dwell_time)
        if trig_config:
            _check_trigger_source(trig_config.source)

        self._sweep = sweep_config or self._sweep
        self._rf = rf_config or self._rf
        self._avg = avg_config or self._avg
        self._trig = trig_config or self._trig

        self._set_path_prefix()

    def get_configuration(self):
        """
        Returns the configuration of the sweeper class as:
        Config(SweepConfig, AvgConfig, RfConfig, TriggerConfig)
        """
        return Config(self._sweep, self._avg, self._rf, self._trig)

    def get_offset_freq_vector(self):
        """
        Get vector of frequency points
        """
        if self._sweep.mapping == _Mapping.LIN.value:
            freq_vec = np.linspace(
                self._sweep.start_freq, self._sweep.stop_freq, self._sweep.num_points
            )
        else:  # log
            start_f_log = np.log10(self._sweep.start_freq + self._rf.center_freq)
            stop_f_log = np.log10(self._sweep.stop_freq + self._rf.center_freq)
            temp_f_vec = np.logspace(start_f_log, stop_f_log, self._sweep.num_points)
            freq_vec = temp_f_vec - self._rf.center_freq

        return freq_vec

    def _set_rf_paths(self):
        # don't set output/input on/off, keep previous user settings
        self._daq.setInt(self._path_prefix + "INPUT/RANGE", self._rf.input_range)
        self._daq.setInt(self._path_prefix + "OUTPUT/RANGE", self._rf.output_range)
        self._daq.setDouble(self._path_prefix + "CENTERFREQ", self._rf.center_freq)
        self._daq.setDouble(
            self._path_prefix + "OSCS/0/GAIN", self._sweep.oscillator_gain
        )
        self._daq.setString(self._path_prefix + "MODE", "spectroscopy")

    def _set_trigger(self):
        path = f"/{self._dev}/RAW/QACHANNELS/{self._rf.channel}/SPECTROSCOPY/TRIGGER/CHANNEL"
        trig_source = _TRIGGER_MAPPING[_TriggerSource(self._trig.source.lower())]
        self._daq.setInt(path, trig_source)
        if trig_source < _HW_TRIGGER_LIMIT:
            # only relevant for HW trigger
            source = trig_source
            trig_channel = source // 2
            trig_input = source % 2
            trig_path = f"/{self._dev}/QACHANNELS/{trig_channel}/TRIGGERS/{trig_input}/"
            self._daq.setDouble(trig_path + "LEVEL", self._trig.level)
            self._daq.setInt(trig_path + "IMP50", self._trig.imp50)

    def _set_path_prefix(self):
        self._path_prefix = f"/{self._dev}/QACHANNELS/{self._rf.channel}/"

    def _wait_for_node(self, node_path, expected_val, time_out=1):
        sleep_time = 0.1
        elapsed_time = 0
        while elapsed_time < time_out:
            val = self._daq.getInt(node_path)
            if val == expected_val:
                return
            time.sleep(sleep_time)
            elapsed_time += sleep_time
        raise TimeoutError(
            f'Node "{node_path}" did not change to {expected_val} within {time_out}sec.'
        )

    def _get_freq_vec(self):
        single_freq_vec = self.get_offset_freq_vector()
        return self._concatenate_freq_vecs(single_freq_vec)

    def _concatenate_freq_vecs(self, single_freq_vec):
        triggered_pointwise = (
            self._avg.mode.lower() == _AveragingMode.POINTWISE.value
            and not self._trig.source.lower() == _TriggerSource.SWTRIGGER.value
        )
        if self._avg.num_samples == 1 or triggered_pointwise:
            freq_vec = single_freq_vec
        elif self._avg.mode == _AveragingMode.SWEEPWISE.value:
            num_concatenate = self._avg.num_samples - 1
            freq_vec = single_freq_vec
            while num_concatenate > 0:
                num_concatenate -= 1
                freq_vec = np.concatenate((freq_vec, single_freq_vec), axis=None)
        else:  # pointwise + sw_trigger
            freq_vec = np.zeros(self._avg.num_samples * self._sweep.num_points)
            for i, f in enumerate(single_freq_vec):
                for j in range(self._avg.num_samples):
                    ind = i * self._avg.num_samples + j
                    freq_vec[ind] = f

        return freq_vec

    def _init_sweep(self):
        self.set_to_device()
        self._reset_result_logger()
        self._init_result_logger()
        self._daq.sync()

    def _reset_result_logger(self):
        reset_path = self._path_prefix + "READOUT/RESULT/RESET"
        self._daq.setInt(reset_path, 1)
        self._daq.sync()
        self._wait_for_node(reset_path, 0)

    def _init_result_logger(self):
        source_spectroscopy = 0
        spectroscopy_len = round(self._avg.dwell_time * self._shf_sample_rate)
        self._daq.setInt(
            self._path_prefix + "READOUT/RESULT/SOURCE", source_spectroscopy
        )
        self._daq.setInt(self._path_prefix + "SPECTROSCOPY/LENGTH", spectroscopy_len)

    def _start_sw_trigger(self):
        self._daq.setInt(f"/{self._dev}/RAW/SYSTEM/SWTRIGGER/START", 1)

    def _enable_measurement(self):
        self._daq.syncSetInt(self._path_prefix + "READOUT/RESULT/ENABLE", 1)

    def _get_data_after_measurement(self):
        self._wait_for_node(self._path_prefix + "READOUT/RESULT/ENABLE", 0)
        data = self._get_result_logger_data()
        return data["vector"]

    def _set_freq_to_device(self, freq):
        self._daq.syncSetDouble(
            f"/{self._dev}/QACHANNELS/{self._rf.channel}/OSCS/0/FREQ", freq
        )

    def _wait_for_results(self, num_results, wait_time):
        self._wait_for_node(
            self._path_prefix + "READOUT/RESULT/ACQUIRED",
            num_results,
            time_out=wait_time,
        )

    def _run_freq_sweep(self):
        self._print_sweep_details()
        freq_vec = self._get_freq_vec()
        self._set_result_len()
        self._enable_measurement()

        for i, freq in enumerate(freq_vec):
            self._set_freq_to_device(freq)
            _print_sweep_progress(freq)
            self._start_sw_trigger()
            self._wait_for_results(i + 1, 2)

        self._result = self._get_data_after_measurement()

    def _run_freq_sweep_trig(self):
        self._print_sweep_details()
        freq_vec = self._get_freq_vec()
        num_results = self._set_result_len()

        self._result = []

        for freq in freq_vec:
            self._set_freq_to_device(freq)
            self._enable_measurement()
            _print_sweep_progress(freq)
            self._wait_for_results(num_results, 10)
            self._result = np.append(self._result, self._get_data_after_measurement())

    def _print_sweep_details(self):
        detail_str = (
            f"Run a sweep with {self._sweep.num_points} frequency points in the range of "
            f"[{self._sweep.start_freq / 1e6}, {self._sweep.stop_freq / 1e6}] MHz + "
            f"{self._rf.center_freq / 1e9} GHz. \n"
            f"Mapping is {self._sweep.mapping}. \n"
            f"Dwell time = {self._avg.dwell_time} sec. \n"
            f"Measures {self._avg.num_samples} times per frequency point. \n"
            f"Averaging mode is {self._avg.mode}."
        )
        print(detail_str)

    def _set_result_len(self):
        if self._trig.source.lower() == _TriggerSource.SWTRIGGER.value:
            num_results = self._sweep.num_points * self._avg.num_samples
        elif self._avg.mode.lower() == _AveragingMode.POINTWISE.value:
            num_results = self._avg.num_samples
        else:
            num_results = 1
        self._daq.setInt(self._path_prefix + "READOUT/RESULT/LENGTH", num_results)
        return num_results

    def _get_result_logger_data(self):
        result_node = self._path_prefix + "READOUT/RESULT/DATA/0/WAVE"
        data = self._daq.get(result_node, flat=True)
        return data[result_node.lower()][0]

    def _average_samples(self, vec):
        if self._avg.num_samples == 1:
            return vec

        avg_vec = np.zeros(self._sweep.num_points, dtype="complex")
        if self._avg.mode == _AveragingMode.SWEEPWISE.value:
            total_measurements = self._sweep.num_points * self._avg.num_samples
            for i in range(self._sweep.num_points):
                avg_range = range(i, total_measurements, self._sweep.num_points)
                avg_vec[i] = np.mean(vec[avg_range])
        else:  # pointwise
            for i in range(self._sweep.num_points):
                start_ind = i * self._avg.num_samples
                avg_range = range(start_ind, start_ind + self._avg.num_samples)
                avg_vec[i] = np.mean(vec[avg_range])

        return avg_vec

    def _check_dwell_time(self, dwell_time_s):
        max_int_len = ((2 ** 23) - 1) * 4
        min_int_len = 4
        max_dwell_time = max_int_len / self._shf_sample_rate
        min_dwell_time = min_int_len / self._shf_sample_rate
        if dwell_time_s < min_dwell_time:
            raise ValueError(f"Dwell time below minimum of {min_dwell_time}s.")
        if dwell_time_s > max_dwell_time:
            raise ValueError(f"Dwell time exceeds maximum of {max_dwell_time}s.")
