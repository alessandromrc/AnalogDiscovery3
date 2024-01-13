from ctypes import *
from dwfconstants import *
import math
import time
import sys
import datetime
import os
import wave
import pyaudio
import numpy as np
import sounddevice as sd

if sys.platform.startswith("win"):
    dwf = cdll.dwf
elif sys.platform.startswith("darwin"):
    dwf = cdll.LoadLibrary("/Library/Frameworks/dwf.framework/dwf")
else:
    dwf = cdll.LoadLibrary("libdwf.so")

# Declare ctype variables
hdwf = c_int()
sts = c_byte()
vOffset = c_double(0)
vAmplitude = c_double(1)
hzAcq = c_double(192000)
cAvailable = c_int()
cLost = c_int()
cCorrupted = c_int()
fLost = 0
fCorrupted = 0

# Open device
print("Opening first device")
dwf.FDwfDeviceOpen(c_int(-1), byref(hdwf))

if hdwf.value == hdwfNone.value:
    szerr = create_string_buffer(512)
    dwf.FDwfGetLastErrorMsg(szerr)
    print(str(szerr.value))
    print("failed to open device")
    quit()

dwf.FDwfDeviceAutoConfigureSet(hdwf, c_int(0))  # 0 = the device will only be configured when FDwf###Configure is called

# Set up acquisition
dwf.FDwfAnalogInChannelEnableSet(hdwf, c_int(0), c_int(1))  # Enable channel 1
dwf.FDwfAnalogInChannelRangeSet(hdwf, c_int(0), c_double(5.0 * vAmplitude.value))
dwf.FDwfAnalogInChannelOffsetSet(hdwf, c_int(0), vOffset)

dwf.FDwfAnalogInChannelEnableSet(hdwf, c_int(1), c_int(1))  # Enable channel 2
dwf.FDwfAnalogInChannelRangeSet(hdwf, c_int(1), c_double(5.0 * vAmplitude.value))
dwf.FDwfAnalogInChannelOffsetSet(hdwf, c_int(1), vOffset)

dwf.FDwfAnalogInAcquisitionModeSet(hdwf, acqmodeRecord)
dwf.FDwfAnalogInFrequencySet(hdwf, hzAcq)
dwf.FDwfAnalogInRecordLengthSet(hdwf, c_double(-1))  # -1 for infinite record length
dwf.FDwfAnalogInConfigure(hdwf, c_int(1), c_int(0))

# Wait at least 2 seconds for the offset to stabilize
time.sleep(2)

print("Starting oscilloscope")
dwf.FDwfAnalogInConfigure(hdwf, c_int(0), c_int(1))

cSamples = 0

p = pyaudio.PyAudio()
output_devices = [p.get_device_info_by_index(i) for i in range(p.get_device_count()) if p.get_device_info_by_index(i)['maxOutputChannels'] > 0]

# Display available output devices
print("Available Output Devices:")
for i, device in enumerate(output_devices):
    print(f"{i + 1}. {device['name']}")

# Let the user select an output device
selected_device_index = int(input("Enter the number of the desired output device: ")) - 1
if not (0 <= selected_device_index < len(output_devices)):
    print("Invalid selection. Exiting.")
    sys.exit()

selected_device = output_devices[selected_device_index]
print(f"Selected Output Device: {selected_device['name']}")

# Set up the output device
output_device = sd.OutputStream(
    channels=2,  # Stereo output
    device=selected_device['index'],  # Use the device index
    samplerate=int(hzAcq.value),
    dtype=np.int16
)


try:
    with output_device:
        while True:
            dwf.FDwfAnalogInStatus(hdwf, c_int(1), byref(sts))
            if cSamples == 0 and (sts == DwfStateConfig or sts == DwfStatePrefill or sts == DwfStateArmed):
                # Acquisition not yet started.
                continue

            dwf.FDwfAnalogInStatusRecord(hdwf, byref(cAvailable), byref(cLost), byref(cCorrupted))

            cSamples += cLost.value

            if cLost.value:
                fLost = 1
            if cCorrupted.value:
                fCorrupted = 1

            if cAvailable.value == 0:
                continue

            # Read data from both channels separately
            left_samples = (c_int16 * cAvailable.value)()
            right_samples = (c_int16 * cAvailable.value)()

            dwf.FDwfAnalogInStatusData16(hdwf, c_int(0), left_samples, c_int(0), cAvailable)
            dwf.FDwfAnalogInStatusData16(hdwf, c_int(1), right_samples, c_int(0), cAvailable)

            # Interleave the samples for stereo playback
            interleaved_samples = np.column_stack((left_samples, right_samples))

            output_device.write(interleaved_samples)

except KeyboardInterrupt:
    pass

dwf.FDwfAnalogOutReset(hdwf, c_int(0))
dwf.FDwfAnalogOutReset(hdwf, c_int(1))
dwf.FDwfDeviceCloseAll()
p.terminate()

print("done")
