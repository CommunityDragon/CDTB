package nl.xupwup.Util;


import java.lang.reflect.Array;
import java.util.Collection;
import java.util.Iterator;
import java.util.List;
import java.util.ListIterator;

/**
 * A ring buffer class which implements the List api.
 *
 * @author Rick
 * @param <T>
 */
public class RingBuffer<T> implements List<T> {

    private Object[] items = null;
    private int start;
    private int size; // end exclusive
    private int preoffset = 0; // only used when this ring is a reflection of another ring
    private int slicelength = -1;
    private RingBuffer<T> actual;

    /**
     * Uses 10 as maximum.
     */
    public RingBuffer() {
        this(10);
    }

    public RingBuffer(int max) {
        items = new Object[max];
        start = 0;
        size = 0;
    }

    private RingBuffer(RingBuffer<T> actual, int fromIndex, int toIndex) {
        items = actual.items;
        start = actual.start;
        preoffset = fromIndex;
        slicelength = toIndex - fromIndex;
        size = actual.size;
        this.actual = actual;
    }

    @Override
    public int size() {
        if (slicelength == -1) {
            return Math.max(size, 0);
        } else {
            return Math.max(Math.min(size - preoffset, slicelength), 0);
        }
    }

    /**
     *
     * @return the maximum amount of items that can fit in this ring.
     */
    public int max() {
        return items.length;
    }

    @Override
    public boolean isEmpty() {
        return size() == 0;
    }

    @Override
    public boolean contains(Object o) {
        return indexOf(o) != -1;
    }

    @Override
    public int indexOf(Object o) {
        for (int i = 0; i < size(); i++) {
            if (get(i) == o) {
                return i;
            }
        }
        return -1;
    }

    @Override
    public int lastIndexOf(Object o) {
        for (int i = size() - 1; i >= 0; i--) {
            if (get(i) == o) {
                return i;
            }
        }
        return -1;
    }

    @Override
    public boolean add(T e) {
        if (slicelength != -1 && size - preoffset >= slicelength) {
            add(slicelength, e);
            if (slicelength < size) {
                slicelength++;
            }
            return true;
        } else {
            items[(start + size) % items.length] = e;
            if (size == items.length) {
                start = (start + 1) % items.length;
            }
            size = Math.min(size + 1, items.length);
            if (slicelength != -1) {
                actual.size = size;
            }
            return true;
        }
    }

    @Override
    public void add(int index, Object element) {
        index = index + preoffset;
        for (int i = size - 1; i >= index; i--) {
            if (i + 1 == size) {
                int sl = slicelength;
                int po = preoffset;
                preoffset = 0;
                slicelength = -1; // act like we are the real ring, so we can properly add to the end.
                add(get(i));
                actual.size = size;
                slicelength = sl; // put it back
                preoffset = po;
            } else {
                set((i + 1) % items.length, get(i));
            }
        }
        set(index, (T) element);
    }

    @Override
    public T get(int index) {
        if (index >= size) {
            throw new IndexOutOfBoundsException("index " + index + " > size (" + size + ")");
        }
        return (T) items[(preoffset + index + start) % items.length];
    }

    @Override
    public T set(int index, T element) {
        if (index == size && size < items.length) {
            add(element);
            return null;
        }
        if (index >= size) {
            throw new IndexOutOfBoundsException("index " + index + " size " + size);
        }
        T prev = get(index);
        items[(preoffset + index + start) % items.length] = element;
        return prev;
    }

    @Override
    public boolean remove(Object o) {
        int idx = indexOf(o);
        if (idx != -1) {
            remove(idx);
            return true;
        }
        return false;
    }

    @Override
    public T remove(int index) {
        T removed = get(index);
        if (index < size() - index) {
            for (int i = index + preoffset; i < size - 1; i++) {
                set(i, get(i + 1));
            }
        } else { // if shifting items in front forward is faster
            for (int i = index + preoffset - 1; i >= 0; i--) {
                // set and get both allow negative indices, so this works
                set(i + 1 - preoffset, get(i - preoffset));
            }
            start++;
        }
        size--;
        if (slicelength != -1) {
            slicelength--;
            actual.size--;
        }
        return removed;
    }

    @Override
    public boolean containsAll(Collection c) {
        for (Object o : c) {
            if (!contains((T) o)) {
                return false;
            }
        }
        return true;
    }

    @Override
    public boolean addAll(Collection c) {
        for (Object o : c) {
            add((T) o);
        }
        return c.size() > 0;
    }

    @Override
    public boolean addAll(int index, Collection c) {
        Object[] toshift = new Object[size() - index];
        for (int i = toshift.length - 1; i >= 0; i--) {
            toshift[i] = remove(i + index);
        }
        addAll(c);
        for (Object o : toshift) {
            add((T) o);
        }
        return c.size() > 0;
    }

    @Override
    public void clear() {
        if (slicelength != -1) {
            removeAll(this);
            return;
        }
        start = 0;
        size = 0;
        for (int i = 0; i < items.length; i++) {
            items[i] = null;
        }
    }

    @Override
    public boolean removeAll(Collection c) {
        boolean r = false;
        for (Object o : c) {
            r = remove((T) o) || r;
        }
        return r;
    }

    @Override
    public boolean retainAll(Collection c) {
        boolean r = false;
        for (int i = 0; i < size(); i++) {
            if (!c.contains(get(i))) {
                remove(i);
                r = true;
            }
        }
        return r;
    }

    @Override
    public Iterator iterator() {
        return listIterator();
    }

    @Override
    public ListIterator listIterator() {
        return new RingBufferIterator(this);
    }

    @Override
    public ListIterator listIterator(int index) {
        RingBufferIterator i = new RingBufferIterator(this);
        i.idx = index;
        return i;
    }

    @Override
    public List subList(int fromIndex, int toIndex) {
        return new RingBuffer(this, fromIndex, toIndex);
    }

    @Override
    public String toString() {
        StringBuilder sb = new StringBuilder("[");
        for (int i = 0; i < size(); i++) {
            if (i != 0) {
                sb.append(", ");
            }
            sb.append(get(i) == null ? "null" : get(i).toString());
        }
        sb.append("]");
        return sb.toString();
    }

    @Override
    public Object[] toArray() {
        Object[] o = new Object[size()];
        for (int i = 0; i < size(); i++) {
            o[i] = get(i);
        }
        return o;
    }

    @Override
    public <U> U[] toArray(U[] a) {
        if (a.length < size()) {
            a = (U[]) Array.newInstance(a.getClass(), size());
        }
        for (int i = 0; i < a.length; i++) {
            a[i] = (U) get(i);
        }
        if (a.length > size()) {
            a[size()] = null;
        }
        return a;
    }

    private class RingBufferIterator implements ListIterator {

        private RingBuffer<T> rb;
        private int idx = -1;

        public RingBufferIterator(RingBuffer<T> rb) {
            this.rb = rb;
        }

        @Override
        public boolean hasNext() {
            return idx + 1 < rb.size();
        }

        @Override
        public Object next() {
            return get(++idx);
        }

        @Override
        public void remove() {
            rb.remove(idx);
        }

        @Override
        public boolean hasPrevious() {
            return idx > 0;
        }

        @Override
        public Object previous() {
            return get(--idx);
        }

        @Override
        public int nextIndex() {
            return idx + 1;
        }

        @Override
        public int previousIndex() {
            return idx - 1;
        }

        @Override
        public void set(Object e) {
            rb.set(idx, (T) e);
        }

        @Override
        public void add(Object e) {
            rb.add(idx, e);
        }
    }
}
