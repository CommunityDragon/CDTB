# Easythreading is an easy to use threading library for python!

## Functionalty and examples:
------

## ring_job:

A ring allows you to execute functions on that ring.
The next ring will execute once all the functions on the ring before have been completed.

### Example 1:
```python
def Hello(text):
	print(text)

manager = ThreadsManager(cores=8) #start thread manager
manager.create_priority_ring(2) #create 2 rings (zero and one)
manager.add_priority_ring_job(Hello,0,args=['Hello 00'])#add function Hello to ring zero with args 'Hello 00'
manager.add_priority_ring_job(Hello,0,args=['Hello 01'])		
manager.add_priority_ring_job(Hello,1,args=['Hello 10'])#add function Hello to ring one with args 'Hello 10'
manager.add_priority_ring_job(Hello,1,args=['Hello 11'])		
manager.start_priority_ring_job() #start the rings going from zero to one
```
Output:
```
Hello 00
Hello 01
Hello 10
Hello 11
```

### Example 2:

If theres an infinate loop function in one of the rings the rings below it wont execute.

```python
def Hello(text):
	print(text)


def infinate_loop(text):
	print(text)
	while 1:
		pass

manager = ThreadsManager(cores=8) #start thread manager
manager.create_priority_ring(2) #create 2 rings (zero and one)
manager.add_priority_ring_job(infinate_loop,0,args=['Hello 00'])#add function infinate_loop to ring zero with args 'Hello 00'
manager.add_priority_ring_job(Hello,0,args=['Hello 01'])		
manager.add_priority_ring_job(Hello,1,args=['Hello 10'])#add function Hello to ring one with args 'Hello 10'
manager.add_priority_ring_job(Hello,1,args=['Hello 11'])		
manager.start_priority_ring_job() #start the rings going from zero to one
```
Output:
```
Hello 00
Hello 01
```
## fork_job:

A fork allows you to create mutiple forked paths this function is just like rings but allows 
you to contine on to the net ring if that fork instance is done with it's ring.

### Example 1:

If theres an infinate loop function in one of the forks the rings below for that fork wont execute.

```python
def Hello(text):
	print(text)


def infinate_loop(text):
	print(text)
	while 1:
		pass

manager = ThreadsManager(cores=8)#start thread manager
manager.create_priority_ring(2)#create 2 rings (zero and one)
manager.add_priority_fork_job(infinate_loop,0,fork=0,args=['Hello 00'])	#add function infinate_loop to ring zero and fork zero with args 'Hello 00'
manager.add_priority_fork_job(Hello,0,fork=1,args=['Hello 01'])	#add function Hello to ring zero and fork one with args 'Hello 01'
manager.add_priority_fork_job(Hello,1,fork=0,args=['Hello 10'])	
manager.add_priority_fork_job(Hello,1,fork=1,args=['Hello 11'])	#add function Hello to ring one and fork one with args 'Hello 11'
manager.start_priority_fork_job() #start each fork going from zero to one
```
Output:
```
Hello 00
Hello 01
Hello 11
```
