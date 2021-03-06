from .base import *
from .linalg import *
from torch import qr as qr
from scipy.linalg import qr as scipy_qr, cho_factor as scipy_cholesky, cho_solve
from scipy.linalg.lapack import dtrtri
from torch import potrf as cholesky, diag, ones, \
				potrs as cholesky_triangular_solve

__all__ = ['qrSolve', 'pinvSolve', 'ridgeSolve', 'choleskySolve']


@check
def qrSolve(X, y):
	'''
	Uses QR Decomposition to solve X * theta = y

	Uses scipy when use_gpu = False, and uses solve_triangular
	to solve R = QTy.

	This implementation of QR Solve handles ill conditioned
	problems using the following algorithm:

	compute covariance XTX
	try Q, R = qr(XTX)
	if R^-1 * R diag sum > 1.1*p {
		compute Q, R = qr(X + I)
	}
	Solves theta =  R^-1 * QT * y
	'''
	XTX = cov(X)

	Q, R = scipy_qr(XTX, mode = 'economic', check_finite = False,
					overwrite_a = True)
	check = 1
	a,b = R.shape
	if use_gpu: R = R.numpy()
	if a == b: _R, check = dtrtri(R)
	if check == 1: _R = pinv(R)

	return _R @ (Q.T @ (X.T @ y))


@check
def pinvSolve(X, y):
	"""
	Solves X*theta_hat = y using pseudoinverse
	on the covariance matrix XTX

	Evaluate pinv(XTX) * (XTy) directly to get theta.
	"""
	return invCov(X, 0, False) @ (T(X) @ y)


@check
def ridgeSolve(X, y, alpha = 1):
	"""
	Solves Ridge Regression directly by evaluating
	the inverse of the covariance matrix + alpha.

	Easily computes:
	theta_hat = pinv(XTX + alpha) * (XTy)
	"""
	return invCov(X, alpha) @ (T(X) @ y)


@check
def choleskySolve(X, y, alpha = 0, step = 10):
	'''
	Solve least squares problem X*theta_hat = y using Cholesky Decomposition.
	
	Alpha = 0, Step = 10 can be options
	Alpha is Regularization Term and step = 10 default for guaranteed stability.
	Step must be > 1
	
	|  Method   |   Operations    | Factor * np^2 |
	|-----------|-----------------|---------------|
	| Cholesky  |   1/3 * np^2    |      1/3      |
	|    QR     |   p^3/3 + np^2  |   1 - p/3n    |
	|    SVD    |   p^3   + np^2  |    1 - p/n    |
	
	NOTE: HyperLearn's implementation of Cholesky Solve uses L2 Regularization to enforce stability.
	Cholesky is known to fail on ill-conditioned problems, so adding L2 penalties helpes it.
	
	Note, the algorithm in this implementation is as follows:
	
		alpha = dtype(X).decimal    [1e-6 is float32]
		while failure {
			solve cholesky ( XTX + alpha*identity )
			alpha *= step (10 default)
		}
	
	If MSE (Mean Squared Error) is abnormally high, it might be better to solve using stabler but
	slower methods like qr_solve, svd_solve or lstsq.
	
	https://www.quora.com/Is-it-better-to-do-QR-Cholesky-or-SVD-for-solving-least-squares-estimate-and-why
	'''
	assert step > 1

	XTX = cov(X)
	alpha = resolution(X) if alpha == 0 else alpha
	regularizer = diagonal(XTX.shape[0], 1, X.dtype)
	
	no_success = True
	warn = False

	while no_success:
		alphaI = regularizer*alpha
		try:
			if use_gpu: chol = cholesky(  XTX + alphaI  )
			else: chol = scipy_cholesky(  XTX + alphaI  , check_finite = False)
			no_success = False
		except:
			alpha *= step
			warn = True
			
	if warn and print_all_warnings:
		print(f'''
		Matrix is not full rank. Added regularization = {alpha} to combat this. 
		Now, solving L2 regularized (XTX+{alpha}*I)^-1(XTy).

		NOTE: It might be better to use svd_solve, qr_solve or lstsq if MSE is high.
		''')
   
	if use_gpu:
		return cholesky_triangular_solve( T(X) @ y, chol).flatten()
	return cho_solve( chol, T(X) @ y ).flatten()
