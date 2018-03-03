# Contributing to CDTB
Welcome! CDTB (short for CommunityDragon Toolbox) is a community project that aims to create tools for downloading and parsing the data from Riot's League of Legends clients such as the LCU, game client and retired League client. If you want to participate, please read the following.


## Getting started
Everything to get you started with working with the CDTB is documented on the README in the base of the project.


## Discussion
Generally, most things are discussed on Discord, click [here](https://discord.gg/rZQwuek) to join the Discord server.

#### Bugs & Issues
Please just report bugs and issues that tend to be pretty small in the issue tracker.

#### Questions
You can just ask those on Discord in the `#general` channel.

#### Suggestions for changes
Either place them in the `#suggestions` channel,  or in the case if the change suggestions are major, send a DM to the management team.


## Submitting code
We work on a PR basis, fork the project and create a PR once you're done. We prefer the commits to be squashed but choice is yours.

## Requirements for submitting code.
1. We're pretty lax of the way the code should look like, if you just follow mainly follow the [PEP 8](https://www.python.org/dev/peps/pep-0008/) standard most things should be fine.
2. We don't require you to be an engineer or rocket scientist, but we do require you to follow a few of these simple princibples.
    * **KISS** (**K**eep **I**t **S**imple, **S**tupid) don't create huge overly complicated functions of hundreds of lines, if you do require big functions, please extract some of the content inside that function and just create a new function out of it. Functions really shouldn't be bigger than 50 lines.
    * **YAGNI** (**Y**ou **A**ren't **G**onna **N**eed **I**t) please don't write code that you we don't require at the time. Most likely it will just go forgotten and make the file bigger without it needing to be bigger (we shouldn't create a project as big as the average node_modules directory of most JS projects)
    * **DRY** (**D**on't **R**epeat **Y**ourself) don't copy paste code multiple times in the project, just reduce it to a function that you can call over and over again. This will make it easier for us all to read and maintain the code.
3. Keep in mind that we will most likely not instantly accept your PR. We might ask for you to create a simple Test that can be used in travis or maybe a change in a variable name. Please don't make a huge deal out of it and just be cooperative with us. We are willing to talk through in detail about why we requested certain changes, and we will never just ask you to change something if we don't think it's necessary. If it really is a major change, feel free to hit us up on discord and let's have a fair and open discussion about it.

## Requirements for participating in the project
Pretty simple, we only got two requests. Please follow the CODE OF CONDUCT and make sure you have fun while helping out the project. If you don't feel like participating, you don't have to. We rather want people that really want to work on it participate than people that generally don't care that much.
