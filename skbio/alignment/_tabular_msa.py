# ----------------------------------------------------------------------------
# Copyright (c) 2013--, scikit-bio development team.
#
# Distributed under the terms of the Modified BSD License.
#
# The full license is in the file COPYING.txt, distributed with this software.
# ----------------------------------------------------------------------------

from __future__ import absolute_import, division, print_function

import collections
import operator

from future.builtins import zip
from future.utils import viewkeys, viewvalues
import numpy as np

from skbio._base import SkbioObject
from skbio.sequence._iupac_sequence import IUPACSequence
from skbio.util import find_duplicates, OperationError, UniqueError
from skbio.util._decorator import experimental
from skbio.util._misc import resolve_key


_Shape = collections.namedtuple('Shape', ['sequence', 'position'])


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
    def get_cached_key(self):
        if self._cached_key is not None:
            return self._cached_key
        else:
            raise OperationError(
                "MSA requires a key but none was provided, and no "
                "cached key exists")

    @experimental(as_of='0.4.0-dev')
    def __init__(self, sequences, key=None, keys=None):
        sequences = iter(sequences)

        self._seqs = []
        self._dtype = None
        self._shape = _Shape(sequence=0, position=0)
        self._cached_key = None

        for seq in sequences:
            self._add_sequence(seq)

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
            self._cached_key = key
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
    def append(self, sequence, key=None):
        """Append a sequence to the MSA.

        Parameters
        ----------
        sequence : IUPACSequence
            Sequence to be appended. Must match the dtype of the MSA and the
            length of the second dimension of the MSA.

        Raises
        ------
        TypeError
            If the type of the sequence does not match the dtype of the MSA.
        ValueError
            If the length of the sequence does not match the length of the
            second dimension of the MSA.

        Notes
        -----
        The MSA is not automatically re-aligned when a sequence is appended.
        Therefore, this operation is not necessarily meaningful on its own.

        Examples
        --------

        """
        if key is None:
            if self.has_keys():
                key = self.get_cached_key()
        else:
            if not self.has_keys():
                raise OperationError(
                    "key was provided but MSA does not have keys.")

        self._add_sequence(sequence)
        self.reindex(key=key)

    def _add_sequence(self, sequence):
        msa_is_empty = not len(self)
        if msa_is_empty:
            dtype = type(sequence)
            if not issubclass(dtype, IUPACSequence):
                raise TypeError(
                    "`sequences` must contain scikit-bio sequence objects "
                    "that have an alphabet, not type %r" % dtype.__name__)
            self._dtype = dtype
            self._shape = _Shape(sequence=1, position=len(sequence))
            self._seqs = [sequence]
        elif type(sequence) != self.dtype:
            raise TypeError(
                "`sequences` cannot contain mixed types. Type %r does "
                "not match type %r" %
                (type(sequence).__name__, self.dtype.__name__))
        elif len(sequence) != self.shape.position:
            raise ValueError(
                "`sequences` must contain sequences of the same "
                "length: %r != %r" % (len(sequence), self.shape.position))
        else:
            self._shape = _Shape(sequence=self._shape.sequence + 1,
                                 position=self._shape.position)
            self._seqs.append(sequence)

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
