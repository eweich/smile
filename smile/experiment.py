#emacs: -*- mode: python; py-indent-offset: 4; indent-tabs-mode: nil -*-
#ex: set sts=4 ts=4 sw=4 et:
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See the COPYING file distributed along with the smile package for the
#   copyright and license terms.
#
### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

# import main modules
#from __future__ import with_statement
import sys
import os
import weakref
import argparse

# pyglet imports
import pyglet
from pyglet.gl import *
from pyglet import clock
from pyglet.window import key,Window

# local imports
from state import Serial, State, RunOnEnter
from ref import val, Ref
from log import dump, yaml2csv

# set up the basic timer
now = clock._default.time
def event_time(time, time_error=0.0):
    return {'time':time, 'error':time_error}
    
class ExpWindow(Window):
    def __init__(self, exp, *args, **kwargs):
        # init the pyglet window
        super(ExpWindow, self).__init__(*args, **kwargs)

        # set up the exp
        self.exp = exp

        # set up easy key logging
        self.keys = key.KeyStateHandler()
        self.push_handlers(self.keys)

        # set empty list of key and mouse handler callbacks
        self.key_callbacks = []
        self.mouse_callbacks = []

        # set up a batch for fast rendering
        # eventually we'll need multiple groups
        self.batch = pyglet.graphics.Batch()

        # say we've got nothing to plot
        self.need_flip = False
        self.need_draw = False

    def on_draw(self, force=False):
        if force or self.need_draw:
            self.clear()
            self.batch.draw()
            self.need_flip = True

    def set_clear_color(self,color=(0,0,0,1)):
        glClearColor(*color)
                
    def on_mouse_motion(self, x, y, dx, dy):
        pass

    def on_mouse_press(self, x, y, button, modifiers):
        for c in self.mouse_callbacks:
            # pass it the x, y, button, mod, and event time
            c(x, y, button, modifiers, self.exp.event_time)
        pass
        
    def on_mouse_release(self, x, y, button, modifiers):
        pass

    def on_mouse_drag(self, x, y, dx, dy, buttons, modifiers):
        pass

    def on_mouse_scroll(self, x, y, scroll_x, scroll_y):
        pass

    def on_key_press(self, symbol, modifiers):
        if (symbol == key.ESCAPE) and (modifiers & key.MOD_SHIFT):
            self.has_exit = True

        # call the registered callbacks
        #print self.key_callbacks
        for c in self.key_callbacks:
            # pass it the key, mod, and event time
            c(symbol, modifiers, self.exp.event_time)

    def on_key_release(self, symbol, modifiers):
        pass

class Experiment(Serial):
    """
    A SMILE experiment.

    This is the top level parent state for all experiments. It handles
    the event loop, manages the window and associated input/output,
    and processes the command line arguments.

    Parameters
    ----------
    fullscreen : bool
        Create the window in full screen.
    resolution : tuple
        Resolution of the window specified as (width, height) when not 
        full screen.
    name : str
        Name on the window title bar.
    pyglet_vsync : bool
        Whether to instruct pyglet to sync to the vertical retrace.
    background_color : tuple
        4 tuple specifying the background color of the experiment 
        window in (R,G,B,A).
    screen_id : int
        What screen/monitor to send the window to in multi-monitor 
        layouts.
    
    Example
    -------
    exp = Experiment(resolution=(1920x1080), background_color=(0,1,0,1.0))
    ...
    run(exp)
    Define an experiment window with a green background and a size of
    1920x1080 pixels. This experiment window will not open until the 
    run() command is executed. 
            
    Log Parameters
    --------------
    All parameters above and below are available to be accessed and 
    manipulated within the experiment code, and will be automatically 
    recorded in the state.yaml and state.csv files. Refer to State class
    docstring for addtional logged parameters.              
    """
    def __init__(self, fullscreen=False, resolution=(800,600), name="Smile",
                 pyglet_vsync=True, background_color=(0,0,0,1), screen_ind=0):

        # first process the args
        self._process_args()
        
        # set up the state
        super(Experiment, self).__init__(parent=None, duration=-1)

        # set up the window
        screens = pyglet.window.get_platform().get_default_display().get_screens()
        if screen_ind != self.screen_ind:
            # command line overrides
            screen_ind = self.screen_ind
        self.screen = screens[screen_ind]
        self.pyglet_vsync = pyglet_vsync
        self.fullscreen = fullscreen or self.fullscreen
        self.resolution = resolution
        self.name = name
        self.window = None   # will create when run

        # set the clear color
        self._background_color = background_color

        # get a clock for sleeping 
        self.clock = pyglet.clock._default

        # set up instance for access throughout code
        self.__class__.last_instance = weakref.ref(self)

        # init parents (with self at top)
        self._parents = [self]
        #global state._global_parents
        #state._global_parents.append(self)

        # we have not flipped yet
        self.last_flip = event_time(0.0)
        
        # event time
        self.last_event = event_time(0.0)

        # default flip interval
        self.flip_interval = 1/60.

        # place to save experimental variables
        self._vars = {}

        # add log locs (state.yaml, experiment.yaml)
        self.state_log = os.path.join(self.subj_dir,'state.yaml')
        self.state_log_stream = open(self.state_log,'a')
        self.exp_log = os.path.join(self.subj_dir,'exp.yaml')
        self.exp_log_stream = open(self.exp_log,'a')

        # # grab the nice
        # import psutil
        # self._current_proc = psutil.Process(os.getpid())
        # cur_nice = self._current_proc.get_nice()
        # print "Current nice: %d" % cur_nice
        # if hasattr(psutil,'HIGH_PRIORITY_CLASS'):
        #     new_nice = psutil.HIGH_PRIORITY_CLASS
        # else:
        #     new_nice = -10
        # self._current_proc.set_nice(new_nice)
        # print "New nice: %d" % self._current_proc.get_nice()

    def _process_args(self):
        # set up the arg parser
        parser = argparse.ArgumentParser(description='Run a SMILE experiment.')
        parser.add_argument("-s", "--subject", 
                            help="unique subject id", 
                            default='test000')        
        parser.add_argument("-f", "--fullscreen", 
                            help="toggle fullscreen", 
                            action='store_true')   
        parser.add_argument("-si", "--screen", 
                            help="screen index", 
                            type=int,
                            default=0)        
        parser.add_argument("-i", "--info", 
                            help="additional run info", 
                            default='')        
        parser.add_argument("-n", "--nocsv", 
                            help="prevent automatic conversion of yaml logs to csv", 
                            action='store_true')   

        # do the parsing
        args = parser.parse_args()

        # set up the subject and subj dir
        self.subj = args.subject
        self.subj_dir = os.path.join('data',self.subj)
        if not os.path.exists(self.subj_dir):
            os.makedirs(self.subj_dir)

        # check for fullscreen
        self.fullscreen = args.fullscreen

        # check screen ind
        self.screen_ind = args.screen

        # set the additional info
        self.info = args.info

        # set whether to log csv
        self.nocsv = args.nocsv
        
    def run(self):
        """
        Run the experiment.
        """
        # create the window
        if self.fullscreen:
            self.window = ExpWindow(self, fullscreen=True, 
                                    caption=self.name, 
                                    vsync=self.pyglet_vsync,
                                    screen=self.screen)
        else:
            self.window = ExpWindow(self, *(self.resolution),
                                    fullscreen=self.fullscreen, 
                                    caption=self.name, 
                                    vsync=self.pyglet_vsync,
                                    screen=self.screen)
            
        # set the clear color
        self.window.set_clear_color(self._background_color)

        # set the mouse as desired
        #self.window.set_exclusive_mouse()
        self.window.set_mouse_visible(False)

        # some gl stuff (must look up to remember why we want them)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

        # get flip interval
        self.flip_interval = self._calc_flip_interval()
        print "Monitor Flip Interval is %f (%f Hz)"%(self.flip_interval,1./self.flip_interval)

        # first clear and do a flip
        #glClear(GL_COLOR_BUFFER_BIT)
        self.window.on_draw(force=True)
        self.blocking_flip()

        # start the first state (that's this experiment)
        self.enter()

        # process events until done
        self._last_time = now()
        while not self.done and not self.window.has_exit:
            # record the time range
            self._new_time = now()
            time_err = (self._new_time - self._last_time)/2.
            self.event_time = event_time(self._last_time+time_err,
                                         time_err)

            # process the events that occurred in that range
            self.window.dispatch_events()

            # handle all scheduled callbacks
            dt = clock.tick(poll=True)

            # put in sleeps if necessary
            if dt < .0001:
                # do a usleep for 1/4 of a ms (might need to tweak)
                self.clock.sleep(250)

            # save the time
            self._last_time = self._new_time

        # write out csv logs if desired
        if not self.nocsv:
            self.state_log_stream.flush()
            yaml2csv(self.state_log, os.path.splitext(self.state_log)[0]+'.csv')
            self.exp_log_stream.flush()
            yaml2csv(self.exp_log, os.path.splitext(self.exp_log)[0]+'.csv')

        # close the window and clean up
        self.window.close()
        self.window = None


    def _calc_flip_interval(self, nflips=55, nignore=5):
        """
        Calculate the mean flip interval.
        """
        import random
        diffs = 0.0
        last_time = 0.0
        count = 0.0
        for i in range(nflips):
            # must draw something so the flip happens
            #color = (random.uniform(0,1),
            #         random.uniform(0,1),
            #         random.uniform(0,1),
            #         1.0)
            color = (0,
                     0,
                     0,
                     1.0)
            self.window.set_clear_color(color)
            self.window.on_draw(force=True)

            # perform the flip and record the flip interval
            cur_time = self.blocking_flip()
            if last_time > 0.0 and i >= nignore:
                diffs += cur_time['time']-last_time['time']
                count += 1
            last_time = cur_time

            # add in sleep of something definitely less than the refresh rate
            self.clock.sleep(5000)  # 5ms for 200Hz

        # reset the background color
        self.window.set_clear_color(self._background_color)
        self.window.on_draw(force=True)
        self.blocking_flip()
        
        # take the mean and return
        return diffs/count
        
    def blocking_flip(self):
        # only flip if we've drawn
        if self.window.need_flip:
            # first the flip
            self.window.flip()

            if True: #not self.pyglet_vsync:
                # OpenGL:
                glDrawBuffer(GL_BACK)
                # We draw our single pixel with an alpha-value of zero
                # - so effectively it doesn't change the color buffer
                # - just the z-buffer if z-writes are enabled...
                glColor4f(0,0,0,0)
                glBegin(GL_POINTS)
                glVertex2i(10,10)
                glEnd()
                # This glFinish() will wait until point drawing is
                # finished, ergo backbuffer was ready for drawing,
                # ergo buffer swap in sync with start of VBL has
                # happened.
                glFinish()

            # return when it happened
            self.last_flip = event_time(now(),0.0)

            # no need for flip anymore
            self.window.need_flip = False

        return self.last_flip


class Set(State, RunOnEnter):
    """
    State to set a experiment variable.

    See Get state for how to access experiment variables.
    
    Parameters
    ----------
    variable : str
        Name of variable to save.
    value : object
        Value to set the variable. Can be a Reference evaluated at 
        runtime.
    eval_var : bool
        If set to 'True,' the variable will be evaluated at runtime.
    parent : {None, ``ParentState``}
        Parent state to attach to. Will search for experiment if None.
    save_log : bool
        If set to 'True,' details about the state will be
        automatically saved in the log files. 
    
    Example
    -------
    See Get state for example.
    
    Log Parameters
    --------------
    All parameters above are available to be accessed and 
    manipulated within the experiment code, and will be automatically 
    recorded in the state.yaml and state.csv files. Refer to State class
    docstring for addtional logged parameters. 
    """
    def __init__(self, variable, value, eval_var=True, parent=None, save_log=True):

        # init the parent class
        super(Set, self).__init__(interval=0, parent=parent, 
                                  duration=0,
                                  save_log=save_log)
        self.var = variable
        self.variable = None
        self.val = value
        self.value = None
        self.eval_var = eval_var

        # append log vars
        self.log_attrs.extend(['variable','value'])
        
    def _callback(self, dt):
        # set the exp var
        if self.eval_var:
            self.variable = val(self.var)
        else:
            self.variable = self.var
        self.value = val(self.val)
        if isinstance(self.variable, str):
            # set the experiment variable
            self.exp._vars[self.variable] = self.value
        elif isinstance(self.variable, Ref):
            # set the ref
            self.variable.set(self.value)
        else:
            raise ValueError('Unrecognized variable type. Must either be string or Ref')

        
def Get(variable):
    """Retrieve an experiment variable.

    Parameters
    ----------
    variable : str
        Name of variable to retrieve. Can be a Reference evaluated 
        at runtime.
        
    Example
    -------
    with Parallel():
        txt = Text('Press a key as quickly as you can!')
        key = KeyPress(base_time=txt['last_flip']['time'])
    Unshow(txt)
    Set('good',key['rt']<0.5)
    with If(Get('good')) as if_state:
        with if_state.true_state:
            Show(Text('Good job!'), duration=1.0)
        with if_state.false_state:
            Show(Text('Better luck next time.'), duration=1.0)
            
    Text will be shown on the screen, instructing the participant to press 
    a key as quickly as they can. The participant will press a key while 
    the text is on the screen, then the text will be removed. The 'Set' 
    state will be used to define a variable for assessing the participant's 
    reaction time for the key press that just occurred, and the 'Get' state 
    accesses that new variable. If the participant's reaction time was 
    faster than 0.5 seconds, the text 'Good job!' will appear on the 
    screen. If the participant's reaction time was slower than 0.5 seconds, 
    the text 'Better luck next time.' will appear on the screen.
    
    Log Parameters
    --------------
    All parameters above are available to be accessed and 
    manipulated within the experiment code, and will be automatically 
    recorded in the state.yaml and state.csv files. Refer to State class
    docstring for addtional logged parameters. 
    """
    gfunc = lambda : Experiment.last_instance()._vars[val(variable)]
    return Ref(gfunc=gfunc)


class Log(State, RunOnEnter):
    """
    State to write values to a custom experiment log.
    Write data to a YAML log file.

    Parameters
    ----------
    log_dict : dict
        Key-value pairs to log. Handy for logging trial information.
    log_file : str, optional
        Where to log, defaults to exp.yaml in the subject directory.
    parent : {None, ``ParentState``}
        Parent state to attach to. Will search for experiment if None.
    **log_items : kwargs
        Key-value pairs to log.
        
    Example
    --------
    numbers_list = [1,2,3]
    with Loop(numbers_list) as trial:
        num = Text(trial.current)
        key = KeyPress()
        Unshow(num)
        
    Log(stim = trial.current,
        response = key['pressed'])
    
    Each number in numbers_list will appear on the screen, and will be
    removed from the screen after the participant presses a key. For each
    trial in the loop, the number that appeared on the screen as well as
    the key that the participant pressed will be recorded in the log files.
    
    Log Parameters
    --------------
    The following information about each state will be stored in addition 
    to the state-specific parameters:

        duration : 
            Duration of the state in seconds. If the duration is not set
            as a parameter of the specific state, it will default to -1 
            (which means it will be calculated on exit) or 0 (which means
            the state completes immediately and does not increment the
            experiment clock).
        end_time :
            Unix timestamp for when the state ended.
        first_call_error
            Amount of time in seconds between when the state was supposed
            to start and when it actually started.
        first_call_time :
            Unix timestamp for when the state was called.
        last_call_error :
            Same as first_call_error, but refers to the most recent time 
            time the state was called.
        last_draw :
            Unix timestamp for when the last draw of a visual stimulus
            occurred.
        last_flip :
            Unix timestamp for when the last flip occurred (i.e., when 
            the stimulus actually appeared on the screen).
        last_update :
            Unix timestamp for the last time the context to be drawn 
            occurred. (NOTE: Displaying a stimulus entails updating it,
            drqwing it to the back buffer, then flipping the front and
            back video buffers to display the stimulus.
        start_time :
            Unix timestamp for when the state is supposed to begin.
        state_time :
            Same as start_time.
    """
    def __init__(self, log_dict=None, log_file=None, parent=None, **log_items):

        # init the parent class
        super(Log, self).__init__(interval=0, parent=parent, 
                                  duration=0,
                                  save_log=False)
        self.log_file = log_file
        self.log_items = log_items
        self.log_dict = log_dict

    def _get_stream(self):
        if self.log_file is None:
            stream = self.exp.exp_log_stream
        else:
            # make it from the name
            stream = open(os.path.join(self.exp.subj_dir,self.log_file),'a')
        return stream
        
    def _callback(self, dt):
        # eval the log_items and write the log
        keyvals = [(k,val(v)) for k,v in self.log_items.iteritems()]
        log = dict(keyvals)
        if self.log_dict:
            log.update(val(self.log_dict))
        # log it to the correct file
        dump([log], self._get_stream())
        pass
    
            
if __name__ == '__main__':
    # can't run inside this file
    #exp = Experiment(fullscreen=False, pyglet_vsync=False)
    #exp.run()
    pass
