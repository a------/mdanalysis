# covariance.py --- Covariance matrix calculations
# Copyright (C) 2014 Wouter Boomsma, Matteo Tiberti
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""
Covariance calculation --- :mod:`encore.covariance`
=====================================================================

The module contains functions to estimate the covariance matrix of
an ensemble of structures.

:Author: Matteo Tiberti, Wouter Boomsma, Tone Bengtsen
:Year: 2015--2016
:Copyright: GNU Public License v3
:Mantainer: Matteo Tiberti <matteo.tiberti@gmail.com>, mtiberti on github

.. versionadded:: 0.14.0
"""

import numpy as np

class EstimatorML(object):
    """
    Standard maximum likelihood estimator of the covariance matrix.
    The generated object acts as a functor.
    """
    @staticmethod
    def calculate(coordinates, reference_coordinates=None):
        """
        Parameters
        ----------

        coordinates : numpy.array
            Flattened array of coordiantes

        reference_coordinates : numpy.array
            Optional reference to use instead of mean

        Returns
        -------

        cov_mat : numpy.array
            Estimate of  covariance matrix

        """

        if reference_coordinates is not None:

            # Offset from reference (for a normal covariance calculation
            # this would be the distance to the average)
            coordinates_offset = coordinates - reference_coordinates

            # Calculate covariance manually
            coordinates_cov = np.zeros((coordinates.shape[1],
                                        coordinates.shape[1]))
            for frame in coordinates_offset:
                coordinates_cov += np.outer(frame, frame)
            coordinates_cov /= coordinates.shape[0]

            return coordinates_cov

        else:
            return np.cov(coordinates, rowvar=0)

    __call__ = calculate


class EstimatorShrinkage(object):
    """
    Shrinkage estimator of the covariance matrix using the method described in

    Improved Estimation of the Covariance Matrix of Stock Returns With an
    Application to Portfolio Selection. Ledoit, O.; Wolf, M., Journal of
    Empirical Finance, 10, 5, 2003

    This implementation is based on the matlab code made available by Olivier
    Ledoit on his website:
    http://www.ledoit.net/ole2_abstract.htm

    The generated object acts as a functor.

    """

    def __init__(self, shrinkage_parameter=None):
        """
        Constructor.

        Parameters
        ----------

        shrinkage_parameter : float
            Makes it possible to set the shrinkage parameter explicitly,
            rather than having it estimated automatically.
        """
        self.shrinkage_parameter = shrinkage_parameter

    def calculate(self, coordinates, reference_coordinates=None):
        """

        Parameters
        ----------

        coordinates : numpy.array
            Flattened array of coordinates
        reference_coordinates: numpy.array
            Optional reference to use instead of mean

        Returns
        --------

        cov_mat : nump.array
            Covariance matrix
        """

        x = coordinates
        t = x.shape[0]
        n = x.shape[1]

        mean_x = np.average(x, axis=0)

        # Use provided coordinates as "mean" if provided
        if reference_coordinates is not None:
            mean_x = reference_coordinates

        x = x - mean_x
        xmkt = np.average(x, axis=1)

        # Call maximum likelihood estimator (note the additional column)
        sample = EstimatorML()(np.hstack([x, xmkt[:, np.newaxis]]), 0) \
            * (t-1)/float(t)

        # Split covariance matrix into components
        covmkt = sample[0:n, n]
        varmkt = sample[n, n]
        sample = sample[:n, :n]

        # Prior
        prior = np.outer(covmkt, covmkt)/varmkt
        prior[np.ma.make_mask(np.eye(n))] = np.diag(sample)

        # If shrinkage parameter is not set, estimate it
        if self.shrinkage_parameter is None:

            # Frobenius norm
            c = np.linalg.norm(sample - prior, ord='fro')**2

            y = x**2
            p = 1/float(t)*np.sum(np.dot(np.transpose(y), y))\
                - np.sum(np.sum(sample**2))
            rdiag = 1/float(t)*np.sum(np.sum(y**2))\
                - np.sum(np.diag(sample)**2)
            z = x * np.repeat(xmkt[:, np.newaxis], n, axis=1)
            v1 = 1/float(t) * np.dot(np.transpose(y), z) \
                - np.repeat(covmkt[:, np.newaxis], n, axis=1)*sample
            roff1 = (np.sum(
                v1*np.transpose(
                    np.repeat(
                        covmkt[:, np.newaxis], n, axis=1)
                    )
                )/varmkt -
                     np.sum(np.diag(v1)*covmkt)/varmkt)
            v3 = 1/float(t)*np.dot(np.transpose(z), z) - varmkt*sample
            roff3 = (np.sum(v3*np.outer(covmkt, covmkt))/varmkt**2 -
                     np.sum(np.diag(v3)*covmkt**2)/varmkt**2)
            roff = 2*roff1-roff3
            r = rdiag+roff

            # Shrinkage constant
            k = (p-r)/c
            self.shrinkage_parameter = max(0, min(1, k/float(t)))

        # calculate covariance matrix
        sigma = self.shrinkage_parameter*prior+(1-self.shrinkage_parameter)*sample

        return sigma

    __call__ = calculate


def covariance_matrix(ensemble,
                      selection="all",
                      estimator=EstimatorShrinkage(),
                      mass_weighted=True,
                      reference=None):
    """
    Calculates (optionally mass weighted) covariance matrix

    Parameters
    ----------

    ensemble : Ensemble object
        The structural ensemble

    selection : str
        Atom selection string in the MDAnalysis format.

    estimator : MLEstimator or ShrinkageEstimator object
        Which estimator type to use (maximum likelihood, shrinkage). This
        object is required to have a __call__ function defined.

    mass_weighted : bool
        Whether to do a mass-weighted analysis

    reference : MDAnalysis.Universe object
        Use the distances to a specific reference structure rather than the
        distance to the mean.

    Returns
    -------

    cov_mat : numpy.array
        Covariance matrix

    """

    # Extract coordinates from ensemble
    coordinates = ensemble.trajectory.timeseries(
        ensemble.select_atoms(selection),
        format='fac')

    # Flatten coordinate matrix into n_frame x n_coordinates
    coordinates = np.reshape(coordinates, (coordinates.shape[0], -1))

    # Extract coordinates from reference structure, if specified
    reference_coordinates = None
    if reference:

        # Select the same atoms in reference structure
        reference_atom_selection = reference.select_atoms(
            ensemble.get_atom_selection_string())
        reference_coordinates = reference_atom_selection.atoms.coordinates()

        # Flatten reference coordinates
        reference_coordinates = reference_coordinates.flatten()

    sigma = estimator(coordinates, reference_coordinates)

    # Optionally correct with mass-weighting
    if mass_weighted:
        # Calculate mass-weighted covariance matrix
        if selection:
            masses = np.repeat(ensemble.select_atoms(selection).masses, 3)
        else:
            masses = np.repeat(ensemble.atoms.masses, 3)
        mass_matrix = np.sqrt(np.identity(len(masses))*masses)
        sigma = np.dot(mass_matrix, np.dot(sigma, mass_matrix))

    return sigma
