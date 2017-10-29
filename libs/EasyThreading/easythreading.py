import threading
import time
from multiprocessing import cpu_count

class Threads:
	
	def __init__(self):
		self.workerlist=[]
		self.kill_dead_workers=True
		self.check_workers_thread = None
		
	def check_workers(self):
		"""remove dead workers"""		
		while self.kill_dead_workers:
			time.sleep(0.1)
			i=0
			a=len(self.workerlist)
			while i<a:
				if self.workerlist[i].isAlive():
					i += 1
				else:
					self.workerlist.pop(i).join()
					a -= 1
					
	def check_workers_thread_start(self):
		self.kill_dead_workers=True
		self.check_workers_thread = threading.Thread(target=self.check_workers)
		self.check_workers_thread.start()

	def check_workers_thread_kill(self):
		self.kill_dead_workers = False
		self.check_workers_thread.join()

	def clean(self):
		self.check_workers_thread_kill()
	
	def initialise(self):
		self.check_workers_thread_start()

	def run(self,func, arg=[]):
		t = threading.Thread(target=func, args=arg)
		t.start()
		self.workerlist.append(t)

class ThreadsManager:
	def __init__(self,cores=-1):
		if cores == -1:
			self.cores = cpu_count()
		elif cores <= 0:
			self.cores = int(cpu_count()*0.75)
		elif cores > cpu_count():
			self.cores = cpu_count()
		else:
			self.cores = int(cores)
		self.priorityJobs=[]

	def add_priority_ring_job(self, func, pri, args=[]):
		self.priorityJobs[pri].append({'func':func, 'args':args})
		
	def add_priority_fork_job(self, func, pri, fork=-1, args=[]):
		priorityJobs = self.priorityJobs[pri]
		if not priorityJobs:
			priorityJobs.append([])
		l = len(priorityJobs[fork])
		if fork >= l:
			priorityJobs.append([])
		priorityJobs[fork].append({'func':func, 'args':args})
		
	def create_priority_ring(self,pri):
		addmore = pri - len(self.priorityJobs)
		if addmore < 0:
			raise IndexError("Cant be under current priority")
		for i in range(addmore):
			self.priorityJobs.append([])

	def are_workers_done(self,thread):
		return(0 == len(thread.workerlist))
		
	def wait_for_workers(self,thread):
		while not self.are_workers_done(thread):
			time.sleep(0.1)#0.1
			
	def limit_cores(self,thread):
		while len(thread.workerlist) >= self.cores:
			time.sleep(0.05)#0.05
			
	def start_priority_ring_job(self):
		thread = Threads()
		thread.initialise()
		for ring in self.priorityJobs:
			for job in ring:
				thread.run(job['func'], arg=job['args'])
				self.limit_cores(thread)
			self.wait_for_workers(thread)
		thread.clean()				
	
	def start_priority_fork_job(self):
		priorityJobs = self.priorityJobs
		threads=[]
		priorityJobs = [i[:-1] for i in priorityJobs]
		priorityJobs = list(map(list, zip(*priorityJobs)))
		for ringJob in priorityJobs:
			manager = ThreadsManager(cores=self.cores)
			manager.priorityJobs = ringJob
			t = threading.Thread(target=manager.start_priority_ring_job)
			threads.append(t)
		
		[t.start() for t in threads]
		[t.join() for t in threads]