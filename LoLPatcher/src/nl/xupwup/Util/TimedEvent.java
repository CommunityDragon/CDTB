/*
 * To change this template, choose Tools | Templates
 * and open the template in the editor.
 */
package nl.xupwup.Util;

import java.util.Arrays;
import java.util.LinkedList;

/**
 *
 * @author rick
 */
public class TimedEvent {
    LinkedList<TimedEventObj> timedEventList = new LinkedList<>();
    
    private class TimedEventObj{
        String name;
        long start;
        long end = -1;
        LinkedList<TimedEventObj> children;
        
        public TimedEventObj(String n){
            start = System.currentTimeMillis();
            children = new LinkedList<>();
            name = n;
        }
        
        public boolean isActive(){
            return end == -1;
        }
        
        /**
         * 
         * @return the last active child, otherwise this.
         */
        public TimedEventObj getLastActiveEvent(){
            if(children.isEmpty()) return this;
            if(children.getLast().isActive())
                return children.getLast().getLastActiveEvent();
            else return this;
        }
        
    }
    /**
     * Time an event. If an event is scheduled while another event is still open the new event
     * is treated as a component of the open event.
     * @param name 
     */
    public void timeEvent(String name){
        if(timedEventList.isEmpty()){
            timedEventList.add(new TimedEventObj(name));
        }else{
            TimedEventObj o = timedEventList.getLast();
            if(o.isActive()){
                o = o.getLastActiveEvent();
                o.children.add(new TimedEventObj(name));
            }else{
                timedEventList.add(new TimedEventObj(name));
            }
        }
    }
    
    /**
     * 
     * @return true if something was finished, othwerwise false
     */
    public boolean finishEvent(){
        TimedEventObj o = timedEventList.getLast();
        if(o.isActive()){
            o = o.getLastActiveEvent();
            o.end = System.currentTimeMillis();
            return true;
        }else{
            return false;
        }
    }
    
    /**
     * Automatically closes all events
     * @modifies this
     * @return 
     */
    @Override
    public String toString(){
        while(finishEvent());
        
        String s = "";
        
        for(TimedEventObj o : timedEventList){
            s += toString(o, 0);
        }
        return s;
    }
    
    private String toString(TimedEventObj o, int ntabs){
        char[] tabs = new char[ntabs];
        Arrays.fill(tabs, '\t');
        String indent = new String(tabs);
        String s = indent + o.name + ": " + (o.end - o.start) + "ms {";
        
        if(o.children.isEmpty()){
            return s + "}";
        }else{
            s += "\n";
            for(TimedEventObj o2 : o.children){
                s += toString(o2, ntabs + 1) + "\n";
            }
            return s + indent+ "}";
        }
        
    }
}
