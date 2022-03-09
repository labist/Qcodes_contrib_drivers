#%%
from pyrf.devices.thinkrf import WSA
from pyrf.sweep_device import SweepDevice
from pyrf.util import capture_spectrum
from pyrf.util import compute_usable_bins


import sys
import time
import math

from matplotlib.pyplot import plot, figure, axis, xlabel, ylabel, show
import numpy as np

from qcodes.instrument.base import Instrument
from qcodes.instrument.parameter import ParameterWithSetpoints, Parameter
from qcodes.dataset.measurements import Measurement
from qcodes.utils.validators import Numbers, Arrays, Enum

# connect to wsa
dut = WSA()
dut.connect('169.254.16.253')
dut.request_read_perm()

## Testing the capture with averages
#%%
# declare sweep constants
RBW = 10e3
F_CENTER = 5.12e9
SPAN = 5e6

TRIGGER_SETTING = {'type': 'NONE',
                'fstart': F_CENTER - SPAN/2, # some value
                'fstop': F_CENTER + SPAN/2,  # some value
                'amplitude': -100}

dut.freq(F_CENTER)
dut.trigger(TRIGGER_SETTING)
dut.scpiset(':SOUR:REF:PLL EXT')

# setup graph
fstart, fstop, spectra_data = capture_spectrum(dut,RBW,average=100)

fig = figure(1)
xvalues = np.linspace(fstart, fstop, len(spectra_data))

xlabel("Frequency")
ylabel("Amplitude")

# plot something
plot(xvalues, spectra_data, color='blue')

# show graph
show()

# %%
