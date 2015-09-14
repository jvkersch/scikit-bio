# ----------------------------------------------------------------------------
# Copyright (c) 2013--, scikit-bio development team.
#
# Distributed under the terms of the Modified BSD License.
#
# The full license is in the file COPYING.txt, distributed with this software.
# ----------------------------------------------------------------------------

from __future__ import absolute_import, division, print_function

import operator

from collections import namedtuple, Counter
from future.builtins import zip
from future.utils import viewkeys, viewvalues
import numpy as np

from skbio._base import SkbioObject
from skbio.sequence._iupac_sequence import IUPACSequence
from skbio.sequence._sequence import Sequence
from skbio.util import find_duplicates, OperationError, UniqueError
from skbio.util._decorator import experimental
from skbio.util._misc import resolve_key


_Shape = namedtuple('Shape', ['sequence', 'position'])


class TabularMSA(SkbioObject):
    """Store a multiple sequence alignment in tabular (row/column) form.

    Parameters
    ----------
    sequences : iterable of alphabet-aware scikit-bio sequence objects
        Aligned sequences in the MSA. Sequences must be the same type, length,
        and have an alphabet. For example, `sequences` could be an iterable of
        ``DNA``, ``RNA``, or ``Protein`` objects.
    key : callable or metadata key, optional
        If provided, defines a unique, hashable key for each sequence in
        `sequences`. Can either be a callable accepting a single argument (each
        sequence) or a key into each sequence's ``metadata`` attribute.
    keys : iterable, optional
        An iterable of the same length as `sequences` containing unique,
        hashable elements. Each element will be used as the respective key for
        `sequences`.

    Raises
    ------
    ValueError
        If `key` and `keys` are both provided.
    ValueError
        If `keys` is not the same length as `sequences`.
    UniqueError
        If keys are not unique.

    See Also
    --------
    skbio.sequence.DNA
    skbio.sequence.RNA
    skbio.sequence.Protein

    Notes
    -----
    If `key` or `keys` are not provided, keys will not be set and certain
    operations requiring keys will raise an ``OperationError``.

    """

    @property
    @experimental(as_of='0.4.0-dev')
    def dtype(self):
        """Data type of the stored sequences.

        Notes
        -----
        This property is not writeable.

        Examples
        --------
        >>> from skbio import DNA, TabularMSA
        >>> msa = TabularMSA([DNA('ACG'), DNA('AC-')])
        >>> msa.dtype
        <class 'skbio.sequence._dna.DNA'>
        >>> msa.dtype is DNA
        True

        """
        return self._dtype

    @property
    @experimental(as_of='0.4.0-dev')
    def shape(self):
        """Number of sequences (rows) and positions (columns).

        Notes
        -----
        This property is not writeable.

        Examples
        --------
        >>> from skbio import DNA, TabularMSA

        Create a ``TabularMSA`` object with 2 sequences and 3 positions:

        >>> msa = TabularMSA([DNA('ACG'), DNA('AC-')])
        >>> msa.shape
        Shape(sequence=2, position=3)
        >>> msa.shape == (2, 3)
        True

        Dimensions can be accessed by index or by name:

        >>> msa.shape[0]
        2
        >>> msa.shape.sequence
        2
        >>> msa.shape[1]
        3
        >>> msa.shape.position
        3

        """
        return self._shape

    @property
    @experimental(as_of='0.4.0-dev')
    def keys(self):
        """Keys in the order of sequences in the MSA.

        Returns
        -------
        np.ndarray (object)
            Immutable 1D array of keys with ``object`` dtype.

        Raises
        ------
        OperationError
            If keys do not exist.

        See Also
        --------
        has_keys
        reindex

        Notes
        -----
        This property can be set and deleted.

        Examples
        --------
        Create a ``TabularMSA`` object keyed by sequence identifier:

        >>> from skbio import DNA, TabularMSA
        >>> seqs = [DNA('ACG', metadata={'id': 'a'}),
        ...         DNA('AC-', metadata={'id': 'b'})]
        >>> msa = TabularMSA(seqs, key='id')

        Retrieve keys:

        >>> msa.keys
        array(['a', 'b'], dtype=object)

        Set keys:

        >>> msa.keys = ['seq1', 'seq2']
        >>> msa.keys
        array(['seq1', 'seq2'], dtype=object)

        To make updates to a subset of the keys, first make a copy of the keys,
        update them, then set them again:

        >>> new_keys = msa.keys.copy()
        >>> new_keys[0] = 'new-key'
        >>> msa.keys = new_keys
        >>> msa.keys
        array(['new-key', 'seq2'], dtype=object)

        Delete keys:

        >>> msa.has_keys()
        True
        >>> del msa.keys
        >>> msa.has_keys()
        False

        """
        if not self.has_keys():
            raise OperationError(
                "Keys do not exist. Use `reindex` to set them.")
        return self._keys

    @keys.setter
    def keys(self, keys):
        self.reindex(keys=keys)

    @keys.deleter
    def keys(self):
        self.reindex()

    @classmethod
    @experimental(as_of="0.4.0-dev")
    def from_dict(cls, dictionary):
        """Create a ``TabularMSA`` from a ``dict``.

        Parameters
        ----------
        dictionary : dict
            Dictionary mapping keys to alphabet-aware scikit-bio sequence
            objects. The ``TabularMSA`` object will have its keys set to the
            keys in the dictionary.

        Returns
        -------
        TabularMSA
            ``TabularMSA`` object constructed from the keys and sequences in
            `dictionary`.

        See Also
        --------
        to_dict
        sort

        Notes
        -----
        The order of sequences and keys in the resulting ``TabularMSA`` object
        is arbitrary. Use ``TabularMSA.sort`` to set a different order.

        Examples
        --------
        >>> from skbio import DNA, TabularMSA
        >>> seqs = {'a': DNA('ACGT'), 'b': DNA('A--T')}
        >>> msa = TabularMSA.from_dict(seqs)

        """
        # Python 2 and 3 guarantee same order of iteration as long as no
        # modifications are made to the dictionary between calls:
        #     https://docs.python.org/2/library/stdtypes.html#dict.items
        #     https://docs.python.org/3/library/stdtypes.html#
        #         dictionary-view-objects
        return cls(viewvalues(dictionary), keys=viewkeys(dictionary))

    @experimental(as_of='0.4.0-dev')
    def __init__(self, sequences, key=None, keys=None):
        sequences = iter(sequences)
        seq = next(sequences, None)

        dtype = None
        length = 0
        seqs = []
        if seq is not None:
            seqs.append(seq)
            dtype = type(seq)
            if not issubclass(dtype, IUPACSequence):
                raise TypeError(
                    "`sequences` must contain scikit-bio sequence objects "
                    "that have an alphabet, not type %r" % dtype.__name__)
            length = len(seq)

            for seq in sequences:
                if type(seq) is not dtype:
                    raise TypeError(
                        "`sequences` cannot contain mixed types. Type %r does "
                        "not match type %r" %
                        (type(seq).__name__, dtype.__name__))
                if len(seq) != length:
                    raise ValueError(
                        "`sequences` must contain sequences of the same "
                        "length: %r != %r" % (len(seq), length))
                seqs.append(seq)

        self._seqs = seqs
        self._dtype = dtype
        self._shape = _Shape(sequence=len(seqs), position=length)
        self.reindex(key=key, keys=keys)

    @experimental(as_of='0.4.0-dev')
    def __bool__(self):
        """Boolean indicating whether the MSA is empty or not.

        Returns
        -------
        bool
            ``False`` if there are no sequences, OR if there are no positions
            (i.e., all sequences are empty). ``True`` otherwise.

        Examples
        --------
        >>> from skbio import DNA, TabularMSA

        MSA with sequences and positions:

        >>> msa = TabularMSA([DNA('ACG'), DNA('AC-')])
        >>> bool(msa)
        True

        No sequences:

        >>> msa = TabularMSA([])
        >>> bool(msa)
        False

        No positions:

        >>> msa = TabularMSA([DNA(''), DNA('')])
        >>> bool(msa)
        False

        """
        # It is impossible to have 0 sequences and >0 positions.
        return self.shape.position > 0

    # Python 2 compatibility.
    __nonzero__ = __bool__

    @experimental(as_of='0.4.0-dev')
    def __len__(self):
        """Number of sequences in the MSA.

        Returns
        -------
        int
            Number of sequences in the MSA (i.e., size of the 1st dimension).

        Notes
        -----
        This is equivalent to ``msa.shape[0]``.

        Examples
        --------
        >>> from skbio import DNA, TabularMSA
        >>> msa = TabularMSA([DNA('ACG'), DNA('AC-')])
        >>> len(msa)
        2
        >>> msa = TabularMSA([])
        >>> len(msa)
        0

        """
        return self.shape.sequence

    @experimental(as_of='0.4.0-dev')
    def __iter__(self):
        """Iterate over sequences in the MSA.

        Yields
        ------
        alphabet-aware scikit-bio sequence object
            Each sequence in the order they are stored in the MSA.

        Examples
        --------
        >>> from skbio import DNA, TabularMSA
        >>> msa = TabularMSA([DNA('ACG'), DNA('AC-')])
        >>> for seq in msa:
        ...     str(seq)
        'ACG'
        'AC-'

        """
        return iter(self._seqs)

    @experimental(as_of='0.4.0-dev')
    def __reversed__(self):
        """Iterate in reverse order over sequences in the MSA.

        Yields
        ------
        alphabet-aware scikit-bio sequence object
            Each sequence in reverse order from how they are stored in the MSA.

        Examples
        --------
        >>> from skbio import DNA, TabularMSA
        >>> msa = TabularMSA([DNA('ACG'), DNA('AC-')])
        >>> for seq in reversed(msa):
        ...     str(seq)
        'AC-'
        'ACG'

        """
        return reversed(self._seqs)

    @experimental(as_of='0.4.0-dev')
    def __str__(self):
        # TODO implement me!
        return super(TabularMSA, self).__str__()

    @experimental(as_of='0.4.0-dev')
    def __eq__(self, other):
        """Determine if this MSA is equal to another.

        ``TabularMSA`` objects are equal if their sequences and keys are equal.

        Parameters
        ----------
        other : TabularMSA
            MSA to test for equality against.

        Returns
        -------
        bool
            Indicates whether this MSA is equal to `other`.

        Examples
        --------
        >>> from skbio import DNA, RNA, TabularMSA
        >>> msa1 = TabularMSA([DNA('ACG'), DNA('AC-')])
        >>> msa1 == msa1
        True

        MSAs with different sequence characters are not equal:

        >>> msa2 = TabularMSA([DNA('ACG'), DNA('--G')])
        >>> msa1 == msa2
        False

        MSAs with different types of sequences (different ``dtype``) are not
        equal:

        >>> msa3 = TabularMSA([RNA('ACG'), RNA('AC-')])
        >>> msa1 == msa3
        False

        MSAs with different sequence metadata are not equal:

        >>> msa4 = TabularMSA([DNA('ACG', metadata={'id': 'a'}), DNA('AC-')])
        >>> msa1 == msa4
        False

        MSAs with different keys are not equal:

        >>> msa5 = TabularMSA([DNA('ACG'), DNA('AC-')], key=str)
        >>> msa1 == msa5
        False

        """
        if not isinstance(other, TabularMSA):
            return False

        # Use np.array_equal instead of (a == b).all():
        #   http://stackoverflow.com/a/10580782/3776794
        return ((self._seqs == other._seqs) and
                np.array_equal(self._keys, other._keys))

    @experimental(as_of='0.4.0-dev')
    def __ne__(self, other):
        """Determine if this MSA is not equal to another.

        ``TabularMSA`` objects are not equal if their sequences or keys are not
        equal.

        Parameters
        ----------
        other : TabularMSA
            MSA to test for inequality against.

        Returns
        -------
        bool
            Indicates whether this MSA is not equal to `other`.

        Examples
        --------
        >>> from skbio import DNA, RNA, TabularMSA
        >>> msa1 = TabularMSA([DNA('ACG'), DNA('AC-')])
        >>> msa1 != msa1
        False

        MSAs with different sequence characters are not equal:

        >>> msa2 = TabularMSA([DNA('ACG'), DNA('--G')])
        >>> msa1 != msa2
        True

        MSAs with different types of sequences (different ``dtype``) are not
        equal:

        >>> msa3 = TabularMSA([RNA('ACG'), RNA('AC-')])
        >>> msa1 != msa3
        True

        MSAs with different sequence metadata are not equal:

        >>> msa4 = TabularMSA([DNA('ACG', metadata={'id': 'a'}), DNA('AC-')])
        >>> msa1 != msa4
        True

        MSAs with different keys are not equal:

        >>> msa5 = TabularMSA([DNA('ACG'), DNA('AC-')], key=str)
        >>> msa1 != msa5
        True

        """
        return not (self == other)

    @experimental(as_of='0.4.0-dev')
    def has_keys(self):
        """Determine if keys exist on the MSA.

        Returns
        -------
        bool
            Indicates whether the MSA has keys.

        See Also
        --------
        keys
        reindex

        Examples
        --------
        >>> from skbio import DNA, TabularMSA
        >>> msa = TabularMSA([DNA('ACG'), DNA('AC-')])
        >>> msa.has_keys()
        False
        >>> msa = TabularMSA([DNA('ACG'), DNA('AC-')], key=str)
        >>> msa.has_keys()
        True

        """
        return self._keys is not None

    @experimental(as_of='0.4.0-dev')
    def reindex(self, key=None, keys=None):
        """Reassign keys to sequences in the MSA.

        Parameters
        ----------
        key : callable or metadata key, optional
            If provided, defines a unique, hashable key for each sequence in
            the MSA. Can either be a callable accepting a single argument (each
            sequence) or a key into each sequence's ``metadata`` attribute.
        keys : iterable, optional
            An iterable of the same length as the number of sequences in the
            MSA. `keys` must contain unique, hashable elements. Each element
            will be used as the respective key for the sequences in the MSA.

        Raises
        ------
        ValueError
            If `key` and `keys` are both provided.
        ValueError
            If `keys` is not the same length as the number of sequences in the
            MSA.
        UniqueError
            If keys are not unique.

        See Also
        --------
        keys
        has_keys

        Notes
        -----
        If `key` or `keys` are not provided, keys will not be set and certain
        operations requiring keys will raise an ``OperationError``.

        Examples
        --------
        Create a ``TabularMSA`` object without keys:

        >>> from skbio import DNA, TabularMSA
        >>> seqs = [DNA('ACG', metadata={'id': 'a'}),
        ...         DNA('AC-', metadata={'id': 'b'})]
        >>> msa = TabularMSA(seqs)
        >>> msa.has_keys()
        False

        Set keys on the MSA, using each sequence's ID:

        >>> msa.reindex(key='id')
        >>> msa.has_keys()
        True
        >>> msa.keys
        array(['a', 'b'], dtype=object)

        Remove keys from the MSA:

        >>> msa.reindex()
        >>> msa.has_keys()
        False

        Alternatively, an iterable of keys may be passed via `keys`:

        >>> msa.reindex(keys=['a', 'b'])
        >>> msa.keys
        array(['a', 'b'], dtype=object)

        """
        if key is not None and keys is not None:
            raise ValueError(
                "Cannot use both `key` and `keys` at the same time.")

        keys_ = None
        if key is not None:
            keys_ = [resolve_key(seq, key) for seq in self._seqs]
        elif keys is not None:
            keys = list(keys)
            if len(keys) != len(self):
                raise ValueError(
                    "Number of elements in `keys` must match number of "
                    "sequences: %d != %d" % (len(keys), len(self)))
            keys_ = keys

        if keys_ is not None:
            # Hashability of keys is implicitly checked here.
            duplicates = find_duplicates(keys_)
            if duplicates:
                raise UniqueError(
                    "Keys must be unique. Duplicate keys: %r" % duplicates)

            # Create an immutable ndarray to ensure key invariants are
            # preserved. Use object dtype to preserve original key types. This
            # is important, for example, because np.array(['a', 42]) will
            # upcast to ['a', '42'].
            keys_ = np.array(keys_, dtype=object, copy=True)
            keys_.flags.writeable = False

        self._keys = keys_

    @experimental(as_of='0.4.0-dev')
    def sort(self, key=None, reverse=False):
        """Sort sequences in-place.

        Performs a stable sort of the sequences in-place.

        Parameters
        ----------
        key : callable or metadata key, optional
            If provided, defines a key to sort each sequence on. Can either be
            a callable accepting a single argument (each sequence) or a key
            into each sequence's ``metadata`` attribute. If not provided,
            sequences will be sorted using existing keys on the ``TabularMSA``.
        reverse: bool, optional
            If ``True``, sort in reverse order.

        Raises
        ------
        OperationError
            If `key` is not provided and keys do not exist on the MSA.

        See Also
        --------
        keys
        has_keys
        reindex

        Notes
        -----
        This method's API is similar to Python's built-in sorting functionality
        (e.g., ``list.sort()``, ``sorted()``). See [1]_ for an excellent
        tutorial on sorting in Python.

        References
        ----------
        .. [1] https://docs.python.org/3/howto/sorting.html

        Examples
        --------
        Create a ``TabularMSA`` object without keys:

        >>> from skbio import DNA, TabularMSA
        >>> seqs = [DNA('ACG', metadata={'id': 'c'}),
        ...         DNA('AC-', metadata={'id': 'b'}),
        ...         DNA('AC-', metadata={'id': 'a'})]
        >>> msa = TabularMSA(seqs)

        Sort the sequences in alphabetical order by sequence identifier:

        >>> msa.sort(key='id')
        >>> msa == TabularMSA([DNA('AC-', metadata={'id': 'a'}),
        ...                    DNA('AC-', metadata={'id': 'b'}),
        ...                    DNA('ACG', metadata={'id': 'c'})])
        True

        Note that since the sort is in-place, the ``TabularMSA`` object is
        modified (a new object is **not** returned).

        Create a ``TabularMSA`` object with keys:

        >>> seqs = [DNA('ACG'), DNA('AC-'), DNA('AC-')]
        >>> msa = TabularMSA(seqs, keys=['c', 'b', 'a'])

        Sort the sequences using the MSA's existing keys:

        >>> msa.sort()
        >>> msa == TabularMSA([DNA('AC-'), DNA('AC-'), DNA('ACG')],
        ...                   keys=['a', 'b', 'c'])
        True

        """
        if key is None:
            sort_keys = self.keys.tolist()
        else:
            sort_keys = [resolve_key(seq, key) for seq in self._seqs]

        if len(self) > 0:
            if self.has_keys():
                _, sorted_seqs, sorted_keys = self._sort_by_first_element(
                    [sort_keys, self._seqs, self.keys.tolist()], reverse)
                self.keys = sorted_keys
            else:
                _, sorted_seqs = self._sort_by_first_element(
                    [sort_keys, self._seqs], reverse)
            self._seqs = list(sorted_seqs)

    def _sort_by_first_element(self, components, reverse):
        """Helper for TabularMSA.sort."""
        # Taken and modified from http://stackoverflow.com/a/13668413/3776794
        return zip(*sorted(
            zip(*components), key=operator.itemgetter(0), reverse=reverse))

    @experimental(as_of='0.4.0-dev')
    def to_dict(self):
        """Create a ``dict`` from this ``TabularMSA``.

        Returns
        -------
        dict
            Dictionary constructed from the keys and sequences in this
            ``TabularMSA``.

        Raises
        ------
        OperationError
            If keys do not exist.

        See Also
        --------
        from_dict
        keys
        has_keys
        reindex

        Examples
        --------
        >>> from skbio import DNA, TabularMSA
        >>> seqs = [DNA('ACGT'), DNA('A--T')]
        >>> msa = TabularMSA(seqs, keys=['a', 'b'])
        >>> dictionary = msa.to_dict()
        >>> dictionary == {'a': DNA('ACGT'), 'b': DNA('A--T')}
        True

        """
        return dict(zip(self.keys, self._seqs))

    @experimental(as_of='0.4.0-dev')
    def iter_positions(self, reverse=False):
        """Generator of MSA positions (i.e., columns)

        Returns
        -------
        GeneratorType
            Generator of generators of positional values in the `TabularMSA`
            (effectively the transpose of the MSA).

        See Also
        --------
        iter

        Examples
        --------
        >>> from skbio import DNA, TabularMSA
        >>> sequences = [DNA('ACCGT--', metadata={'id': "seq1"}),
        ...              DNA('AACCGGT', metadata={'id': "seq2"})]
        >>> msa = TabularMSA(sequences)
        >>> for position in msa.iter_positions():
        ...     for seq in position:
        ...         print(seq.metadata['id'], seq)
        ...     print('')
        seq1 A
        seq2 A
        <BLANKLINE>
        seq1 C
        seq2 A
        <BLANKLINE>
        seq1 C
        seq2 C
        <BLANKLINE>
        seq1 G
        seq2 C
        <BLANKLINE>
        seq1 T
        seq2 G
        <BLANKLINE>
        seq1 -
        seq2 G
        <BLANKLINE>
        seq1 -
        seq2 T
        <BLANKLINE>
        >>> for position in msa.iter_positions(reverse=True):
        ...     for seq in position:
        ...         print(seq.metadata['id'], seq)
        ...     print('')
        seq1 -
        seq2 T
        <BLANKLINE>
        seq1 -
        seq2 G
        <BLANKLINE>
        seq1 T
        seq2 G
        <BLANKLINE>
        seq1 G
        seq2 C
        <BLANKLINE>
        seq1 C
        seq2 C
        <BLANKLINE>
        seq1 C
        seq2 A
        <BLANKLINE>
        seq1 A
        seq2 A
        <BLANKLINE>
        """
        if reverse:
            iterable = reversed(range(self.shape.position))
        else:
            iterable = range(self.shape.position)
        for i in iterable:
            # Inner function is required to close over the current index value
            # for use in the generator. This allows us to return generators
            # without needing to evaluate anything up front.
            def position_with_captured_index_value(index=i):
                return (Sequence(seq[index]) for seq in self)
            position = position_with_captured_index_value()
            yield position

    @experimental(as_of='0.4.0-dev')
    def consensus(self):
        """Return the consensus sequence for the TabularMSA.

        Returns
        -------
        skbio.Sequence
            The consensus sequence of the `TabularMSA`. In other words, at each
            position the most common character is chosen, and those characters
            are combined to create a new sequence. The sequence will not have
            its metadata or positional metadata set; only the sequence will be
            set. The type of biological sequence that is returned will be the
            same type as the first sequence in the alignment, or ``Sequence``
            if the alignment is empty.

        Notes
        -----
        If there are two characters that are equally abundant in the sequence
        at a given position, the choice of which of those characters will be
        present at that position in the result is arbitrary.

        Examples
        --------
        >>> from skbio import TabularMSA
        >>> from skbio import DNA
        >>> sequences = [DNA('AC--', metadata={'id': "seq1"}),
        ...              DNA('AT-C', metadata={'id': "seq2"}),
        ...              DNA('TT-C', metadata={'id': "seq3"})]
        >>> msa = TabularMSA(sequences)
        >>> msa.consensus()
        DNA
        -----------------------------
        Stats:
            length: 4
            has gaps: True
            has degenerates: False
            has non-degenerates: True
            GC-content: 33.33%
        -----------------------------
        0 AT-C

        """

        if self.dtype is not None:
            constructor = self.dtype
        else:
            constructor = Sequence
        return constructor(''.join(c.most_common(1)[0][0]
                           for c in self._position_counters()))

    def _position_counters(self):
        return [Counter([str(seq) for seq in position])
                for position in self.iter_positions()]
