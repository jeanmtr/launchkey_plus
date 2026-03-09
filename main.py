import mido
import time
import sys
import queue
import threading
import soundfile as sf
import numpy as np
import sounddevice as sd
import audiotest

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
        self.events = queue.Queue()
        self.event_thread = threading.Thread(target=self.fetch_events, daemon=True)
        self.event_thread.start()


        #colors are values between 0 and 3 ty partsnotincluded.com
        # there is 18 leds, the last 2 are play buttons
    def fetch_events(self):
        for msg in self.inport:
            self.events.put(msg)
    def led_on(self, led,red,green):
        leds = list(range(8)) + list(range(16,24)) + [8,24]
        self.outport.send(mido.Message('note_on', channel = 0, note = (96 + leds[led]),velocity = (red + (green << 4)) ))

    def led_off(self, led):
        leds = list(range(8)) + list(range(16,24)) + [8,24]
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


class State:
    def __init__(self, machine):
        self.lk = machine.lk
        self.engine = machine.engine
        self.machine = machine
    def on_exit(self): pass
    def on_pad(self, pad, velocity): pass
    def on_control(self, control): pass
    def on_pot(self, pot, value): pass
    def on_tick(self): pass
    def update_leds(self): pass

class SequencerState(State):
    def __init__(self, machine):
        super().__init__(machine)
        self.update_leds()
    
    def update_leds(self):
        for i,led in enumerate(self.engine.patterns[self.engine.current_pattern]):
            if led:
                self.lk.led_on(i,1,1)
            else:
                self.lk.led_off(i)

    def on_pad(self, pad, velocity):
        self.engine.patterns[self.engine.current_pattern][pad] ^= True
        self.update_leds()
    
    def on_tick(self):
        step = self.engine.current_step
        if self.engine.patterns[self.engine.current_pattern][(step-1)%16] == False:
            self.lk.led_off((step-1)%16)
        else:
            self.lk.led_on((step-1)%16,1,1)
        self.lk.led_on(step,1,0)

    def on_control(self,control):
        match control:
            case 106:
                if self.engine.current_pattern > 0:
                    self.engine.current_pattern -= 1
                    self.update_leds()
                    print(self.engine.current_pattern)
            case 107:
                if self.engine.current_pattern < 15:
                    self.engine.current_pattern += 1
                    self.update_leds()
                    print(self.engine.current_pattern)


class StateMachine:
    
    def __init__(self, lk, engine):
        self.engine = engine
        self.lk = lk
        self.current = SequencerState(self)
        self.dispatch_thread = threading.Thread(target=self.dispatch, daemon=True)
        self.event_thread = threading.Thread(target=self.manage_events, daemon=True)
        self.dispatch_thread.start()
        self.event_thread.start()

    def transition(self, new_state: State):
        self.current.on_exit()
        self.current = new_state
    
    def pad_to_seq(self, x):
        seq = list(range(8)) + [16] + 7*[-1] + list(range(8,16)) + [17]
        return seq[x-96]
    
    def manage_events(self):
        while True:
            self.engine.tick.wait()
            self.engine.tick.clear()
            self.current.on_tick()
    def dispatch(self):
        while True:
            msg = self.lk.events.get()
            print(msg)
            match msg.type:
                case "note_on" if msg.channel == 0 and msg.note > 90:
                    self.current.on_pad(self.pad_to_seq(msg.note),msg.velocity)
                case "control_change":
                    if msg.value == 127 and msg.control in [106,107,108,109]:
                        self.current.on_control(msg.control)
                    else :
                        self.current.on_pot(msg.control, msg.value)



class Engine:
    def __init__(self):
        self.running = False
        self.bpm = 110
        self.patterns = [[False for _ in range(16)] for _ in range(16)]
        self.samples = [audiotest.kick,audiotest.hihat,audiotest.clap,audiotest.hihat,[0,0]]
        self.current_pattern = 0
        self.current_step = 0
        self.tick = threading.Event()
        self.clock_thread = threading.Thread(target=self.clock_loop, daemon=True)
        self.sample_thread = threading.Thread(target=self.sample_thread, daemon=True)
        self.sample_thread.start()
        self.clock_thread.start()
        self.running = True
        
        audiotest.stream.start()
    
    def sample_thread(self):
        while True:
            self.tick.wait()
            for i in range(16):
                if self.patterns[i][self.current_step] == True:
                    audiotest.play_sample(self.samples[i])
                    time.sleep(0.001)

    def clock_loop(self):
        step = 60/(self.bpm*4)
        next_time = time.perf_counter()    
        while True:
            if self.running:
                self.current_step = (self.current_step + 1) % 16
                self.tick.set()

            next_time += step
            while time.perf_counter() < next_time:
                time.sleep(0.000001)

    
                

if __name__ == '__main__':
    lk = Launchkey()
    engine = Engine()
    machine = StateMachine(lk, engine)
    try:
        while(True):
            time.sleep(1)
    except KeyboardInterrupt:
        print("ctrl+c pressed")
        lk.disconnect()
        sys.exit(0)
