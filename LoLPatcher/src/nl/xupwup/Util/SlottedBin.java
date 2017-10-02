/*
 * To change this template, choose Tools | Templates
 * and open the template in the editor.
 */
package nl.xupwup.Util;

import java.util.Iterator;

/**
 *
 * @author rick
 */
public class SlottedBin<T> implements Iterable<T> {
    Slot<T>[][] bins;
    int xdim, ydim;
    int xoff, yoff;
    int slotmax;
    int size;
    
    /**
     * Create a slice of another slotted bin.
     * @param lx
     * @param hx
     * @param ly
     * @param hy
     * @param b 
     */
    public SlottedBin(int lx, int hx, int ly, int hy, SlottedBin<T> b){
        bins = new Slot[1 + hy - ly][1 + hx - lx];
        size = 0;
        for(int i = 0; i < bins.length; i++){
            for(int j = 0; j < bins[0].length; j++){
                bins[i][j] = b.bins[ly + i][lx + j];
                size++;
            }
        }
        xoff = (lx / b.bins[0].length) * b.xdim;
        yoff = (ly / b.bins.length) * b.ydim;
        this.xdim = ((hx+1) / b.bins[0].length) * b.xdim - xoff;
        this.ydim = ((hy+1) / b.bins.length) * b.ydim - yoff;
        this.slotmax = b.slotmax;
    }
    
    public SlottedBin(int xslots, int yslots, int xdim, int ydim, int slotMax){
        this(0, 0, xslots, yslots, xdim, ydim, slotMax);
    }
    public SlottedBin(int xoffset, int yoffset, int xslots, int yslots, int xdim, int ydim, int slotMax){
        bins = new Slot[xslots][yslots];
        for(int i = 0; i < xslots; i++){
            for(int j = 0; j < yslots; j++){
                bins[i][j] = new Slot<>(slotMax);
            }
        }
        size = 0;
        this.xdim = xdim;
        this.ydim = ydim;
        xoff = xoffset;
        yoff = yoffset;
        this.slotmax = slotMax;
    }
    
    public void clear(){
        for(int i = 0; i < bins.length; i++){
            for(int j = 0; j < bins[0].length; j++){
                bins[i][j].removeAll();
            }
        }
        size = 0;
    }
    
    /**
     * If the item does not fit in the assigned slot, it will not be added.
     * This function therefore does not guarantee that the item is added to a bin.
     * @param item
     * @param x
     * @param y 
     * @return whether or not the item was actually added.
     */
    public boolean add(T item, int x, int y){
        x -= xoff;
        y -= xoff;
        int xd = (int) Math.min(Math.max(0, (float) x / xdim) * (bins[0].length -1), bins[0].length-1);
        int yd = (int) Math.min(Math.max(0, (float) y / ydim) * (bins.length -1), bins.length-1);
        if(!bins[yd][xd].isFull()){
            bins[yd][xd].add(item);
            size++;
            return true;
        }
        return false;
    }
    
    public int size(){
        return size;
    }
    
    public SlottedBin<T> neighbors(int x, int y){
        x -= xoff;
        y -= xoff;
        int xd = (int) Math.min(Math.max(0, (float) x / xdim) * (bins[0].length -1), bins[0].length-1);
        int yd = (int) Math.min(Math.max(0, (float) y / ydim) * (bins.length -1), bins.length-1);
        
        int lx = Math.max(0, xd - 1);
        int ly = Math.max(0, yd - 1);
        int hx = Math.min(bins[0].length-1, xd + 1);
        int hy = Math.min(bins.length-1, yd + 1);
        
        return new SlottedBin<>(lx, hx, ly, hy, this);
    }

    @Override
    public Iterator<T> iterator() {
        return new Iterator<T>() {
            int x, y;
            int i;
            @Override
            public boolean hasNext() {
                int tmpi = i, tmpx = x, tmpy = y;
                while(tmpi >= bins[tmpy][tmpx].size()){
                    if(tmpx+1 < bins[0].length){
                        tmpx++;
                        tmpi = 0;
                    }else if(tmpy+1 < bins.length){
                        tmpy++;
                        tmpx = 0;
                        tmpi = 0;
                    }else{
                        return false;
                    }
                }
                return true;
            }

            @Override
            public T next() {
                while(i >= bins[y][x].size()){
                    if(x+1 < bins[0].length){
                        x++;
                        i = 0;
                    }else if(y+1 < bins.length){
                        y++;
                        x = 0;
                        i = 0;
                    }else{
                        return null;
                    }
                }
                return bins[y][x].get(i++);
            }

            @Override
            public void remove() {
                throw new UnsupportedOperationException("Not supported yet."); //To change body of generated methods, choose Tools | Templates.
            }
        };
    }
    
    private class Slot<A>{
        Object[] items;
        int count;
        
        public Slot(int max){
            items = new Object[max];
        }
        
        public void add(A item){
            if(count == items.length){
                throw new IndexOutOfBoundsException("Trying to add elements to a full slot. (" + count + " items)");
            }
            items[count] = item;
            count++;
        }
        
        public int size(){
            return count;
        }
        
        public boolean isFull(){
            return count == items.length;
        }
        
        public A get(int i){
            if(i >= count){
                throw new IndexOutOfBoundsException(i+" >= " + count + "");
            }
            return (A) items[i];
        }
        public void removeLast(){
            items[count -1] = null;
            count --;
        }
        
        public void removeAll(){
            while(count > 0){
                removeLast();
            }
        }
    }
}
