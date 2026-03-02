import mido
import time


mido.set_backend('mido.backends.rtmidi')

print(mido.get_output_names())
print(mido.get_input_names())

inport = mido.open_input('Launchkey Mini:Launchkey Mini LK Mini MIDI 20:0')
outport = mido.open_output('Launchkey Mini:Launchkey Mini LK Mini InContro 20:1')

start_incontrol = mido.Message('note_on', note= 12, channel=0, velocity = 127)
outport.send(start_incontrol)
print("set incontrol to on")
time.sleep(1)

#colors are values between 0 and 3 ty partsnotincluded.com
# there is 18 leds
def led_on(led,red,green):
    leds = list(range(9)) + list(range(16,26))
    outport.send(mido.Message('note_on', channel = 0, note = (96 + leds[led]),velocity = (red + (green << 4)) ))

def led_off(led):
    leds = list(range(9)) + list(range(16,26))
    outport.send(mido.Message('note_on', channel = 0, note = (96 + leds[led]),velocity = 0 ))


while(True):
    for i in range(18):
        led_on(i,1,1)
        time.sleep(0.05)
    for i in range(18):
        led_off(i)
        time.sleep(0.05)


stop_incontrol = mido.Message('note_on', note= 12, channel=0, velocity = 0)
outport.send(stop_incontrol)
print("set incontrol to off")

outport.close()
inport.close()
print("everything is done")
