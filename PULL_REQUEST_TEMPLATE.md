1. We're pretty lax of the way the code should look like, if you just follow mainly follow the [PEP 8](https://www.python.org/dev/peps/pep-0008/) standard most things should be fine.

2. We don't require you to be an engineer or rocket scientist, but we do require you to follow a few of these simple princibples.

    * **KISS** (**K**eep **I**t **S**imple, **S**tupid) don't create huge overly complicated functions of hundreds of lines, if you do require big functions, please extract some of the content inside that function and just create a new function out of it. Functions really shouldn't be bigger than 50 lines.
    
    * **YAGNI** (**Y**ou **A**ren't **G**onna **N**eed **I**t) please don't write code that you we don't require at the time. Most likely it will just go forgotten and make the file bigger without it needing to be bigger (we shouldn't create a project as big as the average node_modules directory of most JS projects)
    
    * **DRY** (**D**on't **R**epeat **Y**ourself) don't copy paste code multiple times in the project, just reduce it to a function that you can call over and over again. This will make it easier for us all to read and maintain the code.
    
3. Keep in mind that we will most likely not instantly accept your PR. We might ask for you to create a simple Test that can be used in travis or maybe a change in a variable name. Please don't make a huge deal out of it and just be cooperative with us. We are willing to talk through in detail about why we requested certain changes, and we will never just ask you to change something if we don't think it's necessary. If it really is a major change, feel free to hit us up on discord and let's have a fair and open discussion about it.
