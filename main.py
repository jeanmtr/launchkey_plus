import mido
import time
import sys
import queue
import threading
import soundfile as sf
import numpy as np
import sounddevice as sd

#hardcoded for now, might lead to some problems later
MIDI_INPUT = 'Launchkey Mini:Launchkey Mini LK Mini InContro 16:1'
MIDI_OUTPUT = 'Launchkey Mini:Launchkey Mini LK Mini InContro 16:1' 

class Launchkey:
    def __init__(self):

        self.connected = False
        self.inport = mido.open_input(MIDI_INPUT)
        self.outport = mido.open_output(MIDI_OUTPUT)
        mido.set_backend('mido.backends.rtmidi')
        start_incontrol = mido.Message('note_on', note= 12, channel=0, velocity = 127)
        self.outport.send(start_incontrol)
        print("set incontrol to on")
        assert(MIDI_INPUT in mido.get_input_names())
        assert(MIDI_OUTPUT in mido.get_output_names())
        self.boot_anim()


        #colors are values between 0 and 3 ty partsnotincluded.com
        # there is 18 leds
    def led_on(self, led,red,green):
        leds = list(range(9)) + list(range(16,26))
        self.outport.send(mido.Message('note_on', channel = 0, note = (96 + leds[led]),velocity = (red + (green << 4)) ))

    def led_off(self, led):
        leds = list(range(9)) + list(range(16,26))
        self.outport.send(mido.Message('note_on', channel = 0, note = (96 + leds[led]),velocity = 0 ))

    def boot_anim(self):
        for i in range(18):
            self.led_on(i,1,1)
            time.sleep(0.05)
        for i in range(18):
            self.led_off(i)
            time.sleep(0.05)
    
    def disconnect(self):
        self.boot_anim()
        stop_incontrol = mido.Message('note_on', note= 12, channel=0, velocity = 0)
        self.outport.send(stop_incontrol)
        print("set incontrol to off")

        self.outport.close()
        self.inport.close()
        print("everything is done")

class Sequencer:
    def __init__(self):
        self.running = False
        self.bpm = 110
        self.patterns = [[False for _ in range(16)] for _ in range(16)]
        self.current_pattern = 0
        self.current_step = 0
        self.event_queue = queue.Queue()
        self.lk = Launchkey()
        self.clock_thread = threading.Thread(target=self.clock_loop, daemon=True)
        self.event_thread = threading.Thread(target=self.process_events, daemon=True)
        self.action_thread = threading.Thread(target=self.parse_inputs, daemon=True)
        self.action_thread.start()
        self.clock_thread.start()
        self.event_thread.start()
        self.sequencer_leds = [0,1,2,3,4,5,6,7,9,10,11,12,13,14,15,16]
        
        

        self.patterns[0][1] = True 
        self.patterns[0][6] = True 
        self.patterns[0][13] = True 
        self.running = True
        self.update_leds()

    def pad_to_seq(self, x):
        seq = list(range(8)) + 8*[-1] + list(range(8,16))
        return seq[x-96]

    def parse_inputs(self):
        for msg in self.lk.inport:
            print(msg)
            if msg.channel == 0 and msg.type == "note_on":
                #pb ici avec les play button mais flem
                if msg.note <= 119 and msg.note >= 96:
                    self.patterns[self.current_pattern][self.pad_to_seq(msg.note)] ^= True
                    self.update_leds()
            if msg.channel == 0 and msg.type == "control_change":
                match msg.control:
                    case 106:
                        if self.current_pattern > 0:
                            self.current_pattern -= 1
                            self.update_leds()
                    case 107:
                        if self.current_pattern < 15:
                            self.current_pattern += 1
                            self.update_leds()

     

    def clock_loop(self):
        step = 60/(self.bpm*4)
        next_time = time.perf_counter()    
        while True:
            if self.running:
                self.event_queue.put(self.current_step)
                self.current_step = (self.current_step + 1) % 16

            next_time += step
            while time.perf_counter() < next_time:
                time.sleep(0.0001)

    def process_events(self):
        while True:
            if not self.event_queue.empty():
                step = self.event_queue.get()
                if self.patterns[self.current_pattern][(step-1)%16] == False:
                    self.lk.led_off(self.sequencer_leds[(step-1)%16])
                else:
                    self.lk.led_on(self.sequencer_leds[(step-1)%16],1,1)
                self.lk.led_on(self.sequencer_leds[step],1,0)
    
    def update_leds(self):
        for i,led in enumerate(self.patterns[self.current_pattern]):
            if led:
                self.lk.led_on(self.sequencer_leds[i],1,1)
            else:
                self.lk.led_off(self.sequencer_leds[i])
                

if __name__ == '__main__':
    seq = Sequencer()
    try:
        while(True):
            time.sleep(1)
    except KeyboardInterrupt:
        print("ctrl+c pressed")
        lk.disconnect()
        sys.exit(0)
