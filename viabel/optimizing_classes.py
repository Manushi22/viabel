from abc import ABC, abstractmethod
import tqdm
import autograd.numpy as np
from scipy.stats import t as tdist
from viabel.approximations import MFGaussian



class Optimizer(ABC):
    """An abstract class for optimization
    """
    
    @abstractmethod
    def optimize(self, n_iters, objective, init_param, smoothed_prop=0.2):
        """
        Parameters
        ----------
        n_iters : `int`
            Number of iterations of the optimization
        objective : `function`
            Function for constructing the objective and gradient function
        init_param : `numpy.ndarray`, shape(var_param_dim,)
            Initial values of the variational parameters
        smoothed_prop : `float`, optional
            Proportion of iterations need to compute the iterate average. The default value is 0.2
            
        Returns
        ----------
        Dictionary
            smoothed_opt_param : `numpy.ndarray`, shape(var_param_dim,)
                Iterate averaged estimated variational parameters 
            variational_param_history : `numpy.ndarray`, shape(n_iters, var_param_dim)\
                Estimated variational parameters over all iterations
            value_history : `numpy.ndarray`, shape(n_iters,)
                Estimated loss (ELBO) over all iterations
        """
        pass
    


class StochasticGradientOptimizer(Optimizer):
    """An abstract class of descent direction and a subclass of Optimizer
    """
    def __init__(self, learning_rate):
        self._learning_rate = learning_rate
        
    def optimize(self, n_iters, objective, init_param, smoothed_prop=0.2):
        variational_param = init_param.copy()
        smoothing_window = int(n_iters*smoothed_prop)
        history = None
        value_history = []
        variational_param_history = []
        descent_dir_history = []
        for t in tqdm.trange(n_iters):
            object_val, object_grad = objective(variational_param)
            value_history.append(object_val)
            descent_dir, history = self.descent_direction(object_grad, history)
            variational_param -= self._learning_rate * descent_dir
            variational_param_history.append(variational_param)
            descent_dir_history.append(descent_dir)
        variational_param_history = np.array(variational_param_history)
        variational_param_latter = variational_param_history[-smoothing_window:,:]
        smoothed_opt_param = np.mean(variational_param_latter, axis = 0)    
        return dict(smoothed_opt_param = smoothed_opt_param,
                    variational_param_history = variational_param_history,
                    value_history = np.array(value_history)) 
            
    @abstractmethod
    def descent_direction(self, grad, history):
        """
        Parameters
        -----------
        learning_rate : `float`
            Tuning parameter that determines the step size
        beta : `float`, optional
            Discounting factor for the history. The default value is 0.9
        jitter : `float`, optional
            Smoothing term that avoids division by zero
        
        Returns
        ----------
        descent_dir : `numpy.ndarray`, shape(var_param_dim,)
            Descent direction of the optimization algorithm
        history : `numpy.ndarray`, shape(var_param_dim,)
            History of the decaying estimated squared gradient
        """
        pass


class RMSProp(StochasticGradientOptimizer):
    """
    RMSprop optimization method        
    """
    def __init__(self, learning_rate, beta=0.9, jitter=1e-8):
        self._beta = beta
        self._jitter = jitter
        super().__init__(learning_rate)
        
    def descent_direction(self, grad, history):
        if history is None:
            history  = grad**2
        history = history*self._beta + (1.-self._beta)*grad**2    
        descent_dir = grad / np.sqrt(self._jitter+history)
        return (descent_dir, history)


class AdaGrad(StochasticGradientOptimizer):
    """
    Adagrad optimization method
    """
    def __init__(self, learning_rate, jitter=1e-8):
        self._jitter = jitter
        super().__init__(learning_rate)
        
    def descent_direction(self, grad, history):
        if history is None:
            history = grad**2
        history = history + grad**2   
        descent_dir = grad / np.sqrt(self._jitter+history)
        return (descent_dir, history)



class SASA(Optimizer):
    """A class of Statistical Adaptive Stochastic Gradient Optimizer
        
    Parameters
        ----------
        theta : `float`
            Fraction of the samples to use for testing
        rho : `float`
            Learning rate reducing factor
        W0 : `int`, optional
            Minimum number of samples for tesing The default is 900.
        t_check : `int`, optional
            Period to perform statistical test. The default is 100.
        delta : `float, optional
            Significance level to compute the confidence interval. The default is 0.05. 
        eps : `float`, optional
            Threshold to determine the stopping iterations. The default is 1e-3.
    """
    def __init__(self, sgo, theta, rho, W0 = 1000, t_check = 100, delta = 0.05, eps = 1e-3):
        if not isinstance(sgo, StochasticGradientOptimizer):
            raise ValueError('sgo must be a subclass of StochasticGradientOptimizer')
        self._sgo = sgo
        self._theta = theta
        self._rho = rho
        self._W0 = W0
        self._t_check = t_check
        self._delta = delta
        self._eps = eps
        
    def convergence_check(self, W, Delta_history):
        """
        Parameters
        ----------
        W : `int`
            Window size to use for the convergence check
        Delta_history : `numpy.ndarray`
            Computed Delta values

        Returns
        -------
        bool
            Indicates whether the convergence reached or not
        """
        m = b = np.floor(np.sqrt(W)).astype(int)
        Delta_reshaped = np.reshape(Delta_history[-m*b:],(m,b))
        mu_n = np.mean(Delta_reshaped)
        Delta_batch_means = np.mean(Delta_reshaped,axis=1)
        sigma_n = np.sqrt((m/(b-1))* np.sum((Delta_batch_means - mu_n)**2))
        sd_error = tdist.ppf(1-self._delta/2, df=b-1) * (sigma_n/np.sqrt(m*b))
        lower = mu_n - sd_error
        upper = mu_n + sd_error
        
        if lower<0 and upper>0:
            return True
        else:
            return False
            
        
    def convergence_test(self, n_iters, objective, init_param):
        """
        Parameters
        ----------
        n_iters : `int`
            Number of iterations of the optimization
        objective: `function`
            Function for constructing the objective and gradient function
        init_param : `numpy.ndarray`, shape(var_param_dim,)
            Initial values of the variational parameters
        int_learning_rate: `float`
            Initial learning rate of optimization (step size to reach the (local) minimum)
            
        Returns
        ----------
        Dictionary
            smoothed_opt_param : `numpy.ndarray`, shape(var_param_dim,)
                 Iterate averaged estimated variational parameters 
            variational_param_history : `numpy.ndarray`, shape(n_iters, var_param_dim)
                Estimated variational parameters over all iterations
            value_history : `numpy.ndarray`, shape(n_iters,)
                 Estimated loss (ELBO) over all iterations
        """
        t0 = 0
        history = None
        learning_rate = self._sgo.learning_rate
        variational_param = init_param.copy()
        variational_param_mean = init_param.copy()
        value_history = []
        Delta_history = []
        variational_param_history = []
        for t in tqdm.trange(n_iters):
            object_val, object_grad = objective(variational_param)
            value_history.append(object_val)
            descent_dir, history = self._sgo.descent_direction(object_grad, history)
            variational_param -= learning_rate * descent_dir
            variational_param_history.append(variational_param)
            Delta = np.dot(variational_param,descent_dir) - 0.5*learning_rate*np.sum(descent_dir**2)
            Delta_history.append(Delta)
            W = np.max([np.min([t-t0, self._W0]), np.ceil(self._theta*(t-t0)).astype(int)])
            if (W >= self._W0) and (t % self._t_check == 0):
                convg = self.convergence_check(W, Delta_history)
                if convg == True:
                    m = b = np.floor(np.sqrt(W)).astype(int)
                    learning_rate = self._rho * learning_rate
                    variational_param_mean_prev = variational_param_mean
                    variational_param_mean = np.mean(np.array(variational_param_history[-m*b:]),axis = 0)
                    t0 = t
                    SKL = MFGaussian._kl(variational_param_mean_prev, variational_param_mean) + MFGaussian._kl(variational_param_mean, variational_param_mean_prev)       
            if (SKL/self._rho < self._eps):
                print('Stopping rule reached at', t+1, 'th iteration')
                break
        return dict(smoothed_opt_param = variational_param_mean,
                    variational_param_history = variational_param_history,
                    value_history = np.array(value_history)) 
    