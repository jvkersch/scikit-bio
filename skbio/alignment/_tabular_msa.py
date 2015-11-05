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

from future.builtins import zip, range
from future.utils import viewkeys, viewvalues
import numpy as np

from skbio._base import SkbioObject, MetadataMixin, PositionalMetadataMixin
from skbio.sequence._iupac_sequence import IUPACSequence
from skbio.sequence import Sequence
from skbio.util import find_duplicates, OperationError, UniqueError
from skbio.util._decorator import experimental, classonlymethod, overrides
from skbio.util._misc import resolve_key


_Shape = collections.namedtuple('Shape', ['sequence', 'position'])


class TabularMSA(MetadataMixin, PositionalMetadataMixin, SkbioObject):
    """Store a multiple sequence alignment in tabular (row/column) form.

    Parameters
    ----------
    sequences : iterable of alphabet-aware scikit-bio sequence objects
        Aligned sequences in the MSA. Sequences must be the same type, length,
        and have an alphabet. For example, `sequences` could be an iterable of
        ``DNA``, ``RNA``, or ``Protein`` objects.
    metadata : dict, optional
        Arbitrary metadata which applies to the entire MSA. A shallow copy of
        the ``dict`` will be made.
    positional_metadata : pd.DataFrame consumable, optional
        Arbitrary metadata which applies to each position in the MSA. Must be
        able to be passed directly to ``pd.DataFrame`` constructor. Each column
        of metadata must be the same length as the number of positions in the
        MSA. A shallow copy of the positional metadata will be made.
    minter : callable or metadata key, optional
        If provided, defines a minter which provides a unique, hashable key
        for each sequence in `sequences`. Can either be a callable accepting
        a single argument (each sequence) or a key into each sequence's
        ``metadata`` attribute.
    keys : iterable, optional
        An iterable of the same length as `sequences` containing unique,
        hashable elements. Each element will be used as the respective key for
        `sequences`.

    Raises
    ------
    ValueError
        If `minter` and `keys` are both provided.
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
    If `minter` or `keys` are not provided, keys will not be set and certain
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
        return type(self._seqs[0]) if len(self) > 0 else None

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
        sequence_count = len(self)
        if sequence_count > 0:
            position_count = len(self._seqs[0])
        else:
            position_count = 0
        return _Shape(sequence=sequence_count, position=position_count)

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
        >>> msa = TabularMSA(seqs, minter='id')

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

    @classonlymethod
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
    def __init__(self, sequences, metadata=None, positional_metadata=None,
                 minter=None, keys=None):
        self._seqs = []
        for seq in sequences:
            self._add_sequence(seq)

        MetadataMixin.__init__(self, metadata=metadata)
        PositionalMetadataMixin.__init__(
            self, positional_metadata=positional_metadata)

        self.reindex(minter=minter, keys=keys)

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
    def __contains__(self, key):
        """Determine if a key is in this MSA.

        Parameters
        ----------
        key : hashable
            Key to search for in this MSA.

        Returns
        -------
        bool
            Indicates whether `key` is in this MSA.

        Raises
        ------
        OperationError
            If keys do not exist.

        Examples
        --------
        >>> from skbio import DNA, TabularMSA
        >>> msa = TabularMSA([DNA('ACG'), DNA('AC-')], keys=['key1', 'key2'])
        >>> 'key1' in msa
        True
        >>> 'key2' in msa
        True
        >>> 'key3' in msa
        False

        """
        # TODO: this lookup is O(n). Not worth fixing now because keys will be
        # refactored into Index which supports fast lookups.
        return key in self.keys

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
        return len(self._seqs)

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

        ``TabularMSA`` objects are equal if their sequences, keys, metadata,
        and positional metadata are equal.

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
        >>> msa = TabularMSA([DNA('ACG'), DNA('AC-')])
        >>> msa == msa
        True

        MSAs with different sequence characters are not equal:

        >>> msa == TabularMSA([DNA('ACG'), DNA('--G')])
        False

        MSAs with different types of sequences (different ``dtype``) are not
        equal:

        >>> msa == TabularMSA([RNA('ACG'), RNA('AC-')])
        False

        MSAs with different sequence metadata are not equal:

        >>> msa == TabularMSA([DNA('ACG', metadata={'id': 'a'}), DNA('AC-')])
        False

        MSAs with different keys are not equal:

        >>> msa == TabularMSA([DNA('ACG'), DNA('AC-')], minter=str)
        False

        MSAs with different metadata are not equal:

        >>> msa == TabularMSA([DNA('ACG'), DNA('AC-')],
        ...                   metadata={'id': 'msa-id'})
        False

        MSAs with different positional metadata are not equal:

        >>> msa == TabularMSA([DNA('ACG'), DNA('AC-')],
        ...                   positional_metadata={'prob': [3, 2, 1]})
        False

        """
        if not isinstance(other, TabularMSA):
            return False

        if not MetadataMixin.__eq__(self, other):
            return False

        if not PositionalMetadataMixin.__eq__(self, other):
            return False

        # Use np.array_equal instead of (a == b).all():
        #   http://stackoverflow.com/a/10580782/3776794
        return ((self._seqs == other._seqs) and
                np.array_equal(self._keys, other._keys))

    @experimental(as_of='0.4.0-dev')
    def __ne__(self, other):
        """Determine if this MSA is not equal to another.

        ``TabularMSA`` objects are not equal if their sequences, keys,
        metadata, or positional metadata are not equal.

        Parameters
        ----------
        other : TabularMSA
            MSA to test for inequality against.

        Returns
        -------
        bool
            Indicates whether this MSA is not equal to `other`.

        See Also
        --------
        __eq__

        """
        return not (self == other)

    @experimental(as_of='0.4.0-dev')
    def gap_frequencies(self, axis='sequence', relative=False):
        """Compute frequency of gap characters across an axis.

        Parameters
        ----------
        axis : {'sequence', 'position'}, optional
            Axis to compute gap character frequencies across. If 'sequence' or
            0, frequencies are computed for each position in the MSA. If
            'position' or 1, frequencies are computed for each sequence.
        relative : bool, optional
            If ``True``, return the relative frequency of gap characters
            instead of the count.

        Returns
        -------
        1D np.ndarray (int or float)
            Vector of gap character frequencies across the specified axis. Will
            have ``int`` dtype if ``relative=False`` and ``float`` dtype if
            ``relative=True``.

        Raises
        ------
        ValueError
            If `axis` is invalid.

        Notes
        -----
        If there are no positions in the MSA, ``axis='position'``, **and**
        ``relative=True``, the relative frequency of gap characters in each
        sequence will be ``np.nan``.

        Examples
        --------
        Compute frequency of gap characters for each position in the MSA (i.e.,
        *across* the sequence axis):

        >>> from skbio import DNA, TabularMSA
        >>> msa = TabularMSA([DNA('ACG'),
        ...                   DNA('A--'),
        ...                   DNA('AC.'),
        ...                   DNA('AG.')])
        >>> msa.gap_frequencies()
        array([0, 1, 3])

        Compute relative frequencies across the same axis:

        >>> msa.gap_frequencies(relative=True)
        array([ 0.  ,  0.25,  0.75])

        Compute frequency of gap characters for each sequence (i.e., *across*
        the position axis):

        >>> msa.gap_frequencies(axis='position')
        array([0, 2, 1, 1])

        """
        if self._is_sequence_axis(axis):
            # TODO: use TabularMSA.iter_positions when it is implemented
            # (#1100).
            seq_iterator = (self._get_position(i)
                            for i in range(self.shape.position))
            length = self.shape.sequence
        else:
            seq_iterator = self
            length = self.shape.position

        gap_freqs = []
        for seq in seq_iterator:
            # Not using Sequence.frequencies(relative=relative) because each
            # gap character's relative frequency is computed separately and
            # must be summed. This is less precise than summing the absolute
            # frequencies of gap characters and dividing by the length. Likely
            # not a big deal for typical gap characters ('-', '.') but can be
            # problematic as the number of gap characters grows (we aren't
            # guaranteed to always have two gap characters). See unit tests for
            # an example.
            freqs = seq.frequencies(chars=self.dtype.gap_chars)
            gap_freqs.append(sum(viewvalues(freqs)))

        gap_freqs = np.asarray(gap_freqs, dtype=float if relative else int)

        if relative:
            gap_freqs /= length

        return gap_freqs

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
        >>> msa = TabularMSA([DNA('ACG'), DNA('AC-')], minter=str)
        >>> msa.has_keys()
        True

        """
        return self._keys is not None

    @experimental(as_of='0.4.0-dev')
    def reindex(self, minter=None, keys=None):
        """Reassign keys to sequences in the MSA.

        Parameters
        ----------
        minter : callable or metadata key, optional
            If provided, defines a minter which provides a unique, hashable
            key for each sequence in the MSA. Can either be a callable
            accepting a single argument (each sequence) or a key into each
            sequence's ``metadata`` attribute.
        keys : iterable, optional
            An iterable of the same length as the number of sequences in the
            MSA. `keys` must contain unique, hashable elements. Each element
            will be used as the respective key for the sequences in the MSA.

        Raises
        ------
        ValueError
            If `minter` and `keys` are both provided.
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
        If `minter` or `keys` are not provided, keys will not be set and
        certain operations requiring keys will raise an ``OperationError``.

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

        >>> msa.reindex(minter='id')
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
        if minter is not None and keys is not None:
            raise ValueError(
                "Cannot use both `minter` and `keys` at the same time.")

        if minter is not None:
            keys_ = [resolve_key(seq, minter) for seq in self._seqs]
        elif keys is not None:
            keys_ = list(keys)
            if len(keys_) != len(self):
                raise ValueError(
                    "Number of elements in `keys` must match number of "
                    "sequences: %d != %d" % (len(keys_), len(self)))
        else:
            keys_ = None

        self._keys = self._munge_keys(keys_)

    def _munge_keys(self, keys):
        if keys is not None:
            # Hashability of keys is implicitly checked here.
            duplicates = find_duplicates(keys)
            if duplicates:
                raise UniqueError(
                    "Keys must be unique. Duplicate keys: %r" % duplicates)

            # Create an immutable ndarray to ensure key invariants are
            # preserved. Use object dtype to preserve original key types. This
            # is important, for example, because np.array(['a', 42]) will
            # upcast to ['a', '42'].
            keys = np.array(keys, dtype=object, copy=True)
            keys.flags.writeable = False
        return keys

    @experimental(as_of='0.4.0-dev')
    def append(self, sequence, minter=None, key=None):
        """Append a sequence to the MSA.

        Parameters
        ----------
        sequence : alphabet-aware scikit-bio sequence object
            Sequence to be appended. Must match the dtype of the MSA and the
            number of positions in the MSA.
        minter : callable or metadata key, optional
            Used to create a key for the sequence being appended. If callable,
            it generates a key directly. Otherwise it's treated as a key into
            the sequence metadata. If the key is a duplicate of any key
            already in the MSA, an error is raised. Note that `minter` cannot
            be combined with `key`.
        key : hashable, optional
            Key for the MSA to use for the appended sequence. Note that
            `key` cannot be combined with `minter`.

        Raises
        ------
        OperationError
            If both key and minter are provided.
        OperationError
            If MSA has keys but no key or minter was provided for the sequence
            being appended.
        OperationError
            If key was provided but the MSA does not have keys.
        OperationError
            If minter was provided but the MSA does not have keys.
        TypeError
            If the sequence object is a type that doesn't have an alphabet
        TypeError
            If the type of the sequence does not match the dtype of the MSA.
        ValueError
            If the length of the sequence does not match the number of
            positions in the MSA.

        See Also
        --------
        reindex

        Notes
        -----
        The MSA is not automatically re-aligned when a sequence is appended.
        Therefore, this operation is not necessarily meaningful on its own.

        Examples
        --------
        >>> from skbio import DNA, TabularMSA
        >>> msa = TabularMSA([DNA('')])
        >>> msa.append(DNA(''))
        >>> msa == TabularMSA([DNA(''), DNA('')])
        True

        >>> msa = TabularMSA([DNA('', metadata={'id': 'a'})], minter='id')
        >>> msa.append(DNA('', metadata={'id': 'b'}), minter='id')
        >>> msa == TabularMSA([DNA('', metadata={'id': 'a'}),
        ...                    DNA('', metadata={'id': 'b'})], minter='id')
        True
        """

        if key is not None and minter is not None:
            raise ValueError(
                "Cannot use both `minter` and `key` at the same time.")

        new_key = None
        if self.has_keys():
            if key is None and minter is None:
                raise OperationError(
                    "MSA has keys but no key or minter was provided.")
            elif key is not None:
                new_key = key
            elif minter is not None:
                new_key = resolve_key(sequence, minter)
        else:
            if key is not None:
                raise OperationError(
                    "key was provided but MSA does not have keys.")
            elif minter is not None:
                raise OperationError(
                    "minter was provided but MSA does not have keys.")

        self._add_sequence(sequence, new_key)

    def _add_sequence(self, sequence, key=None):
        msa_is_empty = not len(self)
        dtype = type(sequence)
        if msa_is_empty:
            if not issubclass(dtype, IUPACSequence):
                raise TypeError(
                    "`sequence` must be a scikit-bio sequence object "
                    "that has an alphabet, not type %r" % dtype.__name__)
            if key is not None:
                self._keys = self._munge_keys([key])
            self._seqs = [sequence]
        elif dtype is not self.dtype:
            raise TypeError(
                "`sequence` must match the type of any other sequences "
                "already in the MSA. Type %r does not match type %r" %
                (dtype.__name__, self.dtype.__name__))
        elif len(sequence) != self.shape.position:
            raise ValueError(
                "`sequence` length must match the number of positions in the "
                "MSA: %d != %d"
                % (len(sequence), self.shape.position))
        else:
            if key is not None:
                keys = list(self.keys)
                keys.append(key)
                self._keys = self._munge_keys(keys)
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

    def _get_position(self, i):
        seq = Sequence.concat([s[i] for s in self._seqs], how='outer')
        if self.has_positional_metadata():
            seq.metadata = dict(self.positional_metadata.iloc[i])
        return seq

    def _is_sequence_axis(self, axis):
        if axis == 'sequence' or axis == 0:
            return True
        elif axis == 'position' or axis == 1:
            return False
        else:
            raise ValueError(
                "`axis` must be 'sequence' (0) or 'position' (1), not %r"
                % axis)

    @overrides(PositionalMetadataMixin)
    def _positional_metadata_axis_len_(self):
        return self.shape.position
