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
MIDI_INPUT = 'Launchkey Mini:Launchkey Mini LK Mini InContro 20:1'
MIDI_OUTPUT = 'Launchkey Mini:Launchkey Mini LK Mini InContro 20:1' 
PPQN = 24

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
    
    def _rev_blink_led_worker(self, led, red, green, t):
        self.led_off(led)
        time.sleep(t)
        self.led_on(led, red, green)

    def rev_blink_led(self, led, red, green, time):
        thread = threading.Thread(target=self._rev_blink_led_worker, daemon=True, args = (led,red,green,time))
        thread.start()
    def boot_anim(self):
        for i in range(18):
            self.led_on(i,1,1)
            time.sleep(0.01)
        for i in range(18):
            self.led_off(i)
            time.sleep(0.01)
    
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

class SampleState(State):
    def __init__(self, machine):
        super().__init__(machine)
        self.update_leds()

    def update_leds(self):
        for i,sample in enumerate(self.engine.samples):
            print(sample)
            if len(sample) > 1:
                self.lk.led_on(i,1,0)
            else:
                self.lk.led_off(i)
            if self.engine.running == False:
                self.lk.led_off(16)
    def on_tick(self):
        for i in range(16):
            if len(self.engine.samples[i]) > 1 and self.engine.patterns[i][self.engine.current_step]:
                self.lk.rev_blink_led(i,1,0,0.03)
        if self.engine.current_step % 24 == 0:
            self.lk.rev_blink_led(16,1,0,0.05)
    def on_pad(self, pad, velocity):
        if pad < 16 and len(engine.samples[pad]) > 1:
            self.machine.transition(SequencerState(self.machine, pad))
        elif pad == 16:
            self.engine.running ^= True
            self.update_leds()
            


class SequencerState(State):
    def __init__(self, machine, pattern):
        super().__init__(machine)
        self.division = 8
        self.current_pattern = pattern


        self.update_leds()
    
    def update_leds(self):
        for i,led in enumerate(self.engine.patterns[self.current_pattern]):
            if i % self.division == 0:
                print(i,i//self.division)
                if led:
                    self.lk.led_on(i//self.division,1,1)
                else:
                    self.lk.led_off(i//self.division)

    def on_pad(self, pad, velocity):
        if pad*self.division < 96:
            self.engine.patterns[self.current_pattern][pad*self.division] ^= True
            self.update_leds()
    
    def on_tick(self):
        step = self.engine.current_step
        visual_step = step//self.division
        nb_notes = 96//self.division
        if step % self.division == 0:
            if self.engine.patterns[self.current_pattern][(step-self.division)%96] == False:
                self.lk.led_off((visual_step-1)%nb_notes)
            else:
                self.lk.led_on((visual_step-1)%nb_notes,1,1)
            self.lk.led_on(visual_step,1,0)

    def on_control(self,control):
        match control:
            case 104:
                print("lmsqkdf")
                self.machine.transition(SampleState(self.machine))
            case 106:
                if self.current_pattern > 0:
                    self.current_pattern -= 1
                    self.update_leds()
                    print(self.current_pattern)
            case 107:
                if self.current_pattern < 15:
                    self.current_pattern += 1
                    self.update_leds()
                    print(self.current_pattern)


class StateMachine:
    
    def __init__(self, lk, engine):
        self.engine = engine
        self.lk = lk
        self.current = SampleState(self)
        self.dispatch_thread = threading.Thread(target=self.dispatch, daemon=True)
        self.event_thread = threading.Thread(target=self.manage_events, daemon=True)
        self.dispatch_thread.start()
        self.event_thread.start()

    def transition(self, new_state: State):
        print("switching to new state")
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
                    if msg.value == 127 and msg.control in [104,105,106,107]:
                        self.current.on_control(msg.control)
                    else :
                        self.current.on_pot(msg.control, msg.value)



class Engine:
    def __init__(self):
        self.running = False
        self.bpm = 110
        self.patterns = [[False for _ in range(96)] for _ in range(16)]
        self.samples = [audiotest.kick,audiotest.hihat,audiotest.clap,audiotest.hihat] + 13 * [[0]]
        self.current_step = 0
        self.tick = threading.Event()
        self.play_queue = queue.Queue()
        self.clock_thread = threading.Thread(target=self.clock_loop, daemon=True)
        self.sample_thread = threading.Thread(target=self.sample_thread, daemon=True)

        self.sample_thread.start()
        self.clock_thread.start()
        
        audiotest.stream.start()
    
    def sample_thread(self):
        while True:
            self.play_queue.get()
            for i in range(16):
                if self.patterns[i][self.current_step] == True:
                    audiotest.play_sample(self.samples[i])

    def clock_loop(self):
        eps = 0.000001
        step = 60/(self.bpm*24)
        next_time = time.perf_counter()    
        while True:
            if self.running:
                self.current_step = (self.current_step + 1) % 96
                self.tick.set()
                self.play_queue.put("tick")

            next_time += step
            while time.perf_counter() < next_time:
                time.sleep(next_time -time.perf_counter())

    
                

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
