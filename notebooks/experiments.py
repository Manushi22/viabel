import numpy as np

import matplotlib.pyplot as plt
import seaborn as sns
all
from viabel import all_bounds
from viabel.vb import black_box_klvi, black_box_chivi, adagrad_optimize
from utils import Timer
from psis import psislw


## Display bounds information ##

def print_bounds(results):
    print('Bounds on...')
    print('  2-Wasserstein: {:.3g}'.format(results['W2']))
    print('  2-divergence:  {:.3g}'.format(results['d2']))
    print('  mean error:    {:.3g}'.format(results['mean_error']))
    print('  stdev error:   {:.3g}'.format(results['std_error']))


## Convenience functions and PSIS ##

def get_samples_and_log_weights(logdensity, var_family, var_param, n_samples):
    samples = var_family.sample(var_param, n_samples)
    log_weights = logdensity(samples) - var_family.logdensity(samples, var_param)
    return samples, log_weights


def psis_correction(logdensity, var_family, var_param, n_samples):
    samples, log_weights = get_samples_and_log_weights(logdensity, var_family,
                                                       var_param, n_samples)
    smoothed_log_weights, khat = psislw(log_weights)
    return samples.T, smoothed_log_weights, khat


def improve_with_psis(logdensity, var_family, var_param, n_samples,
                      true_mean, true_cov, transform=None, verbose=False):
    samples, slw, khat = psis_correction(logdensity, var_family,
                                         var_param, n_samples)
    if verbose:
        print('khat = {:.3g}'.format(khat))
    if transform is not None:
        samples = transform(samples)
    slw -= np.max(slw)
    wts = np.exp(slw)
    wts /= np.sum(wts)
    approx_mean = np.sum(wts[np.newaxis,:]*samples, axis=1)
    approx_cov = np.cov(samples, aweights=wts, ddof=0)
    res = check_accuracy(true_mean, true_cov, approx_mean, approx_cov, verbose)
    res['khat'] = khat
    return res, approx_mean, approx_cov


## Check approximation accuracy ##

def check_accuracy(true_mean, true_cov, approx_mean, approx_cov, verbose=False,
                   method=None):
    true_std = np.sqrt(np.diag(true_cov))
    approx_std = np.sqrt(np.diag(approx_cov))
    results = dict(mean_error=np.linalg.norm(true_mean - approx_mean),
                   cov_error_2=np.linalg.norm(true_cov - approx_cov, ord=2),
                   cov_norm_2=np.linalg.norm(true_cov, ord=2),
                   cov_error_nuc=np.linalg.norm(true_cov - approx_cov, ord='nuc'),
                   cov_norm_nuc=np.linalg.norm(true_cov, ord='nuc'),
                   std_error=np.linalg.norm(true_std - approx_std),
                   rel_std_error=np.linalg.norm(approx_std/true_std - 1),
                  )
    if method is not None:
        results['method'] = method
    if verbose:
        print('mean   =', approx_mean)
        print('stdevs =', approx_std)
        print('mean error       = {:.3g}'.format(results['mean_error']))
        print('||cov error||_2  = {:.3g}'.format(results['cov_error_2']))
        print('||true_cov||_2   = {:.3g}'.format(results['cov_norm_2']))
        print('stdev error      = {:.3g}'.format(results['std_error']))
        print('rel. std error   = {:.3g}'.format(results['rel_std_error']))
    return results


def check_approx_accuracy(var_family, var_param, true_mean, true_cov,
                          verbose=False, name=None):
    return check_accuracy(true_mean, true_cov,
                          *var_family.mean_and_cov(var_param),
                          verbose, name)


## Plotting ##

def plot_approx_and_exact_contours(logdensity, var_family, var_param,
                                   xlim=[-10,10], ylim=[-3, 3]):
    xlist = np.linspace(*xlim, 100)
    ylist = np.linspace(*ylim, 100)
    X, Y = np.meshgrid(xlist, ylist)
    XY = np.concatenate([X[:,:,np.newaxis], Y[:,:,np.newaxis]], axis=2)
    Z = np.exp(logdensity(XY))
    Zapprox = np.exp(var_family.logdensity(XY, var_param))
    plt.contour(X, Y, Z, colors='k', linestyles='solid')
    plt.contour(X, Y, Zapprox, colors='r', linestyles='solid')
    plt.show()


def plot_history(history, B=None, ylabel=None):
    if B is None:
        B = min(500, history.size//10)
    window = np.ones(B)/B
    smoothed_history = np.convolve(history, window, 'valid')
    plt.plot(smoothed_history)
    yscale = 'log' if np.all(smoothed_history > 0) else 'linear'
    plt.yscale(yscale)
    if ylabel is not None:
        plt.ylabel(ylabel)
    plt.xlabel('iteration')
    plt.show()


## Run experiment with both KLVI and CHIVI ##

def _optimize_and_check_results(logdensity, var_family, objective_and_grad,
                                init_var_param, true_mean, true_cov,
                                plot_contours, ylabel, contour_kws=dict(),
                                elbo=None, n_iters=5000,
                                bound_w2=True, verbose=False, use_psis=True,
                                n_psis_samples=1000000, **kwargs):
    opt_param, var_param_history, value_history, _ = \
        adagrad_optimize(n_iters, objective_and_grad, init_var_param, **kwargs)
    smoothed_opt_param = np.mean(var_param_history, axis=0)
    plt.plot(np.linalg.norm(var_param_history - smoothed_opt_param[np.newaxis,:], axis=1))
    plt.title('iteration vs distance to smoothed optimal parameter')
    plt.xlabel('iteration')
    plt.ylabel('distance')
    sns.despine()
    plt.show()
    plt.close()
    accuracy_results = check_approx_accuracy(var_family, opt_param, true_mean,
                                             true_cov, verbose);
    other_results = dict(opt_param=opt_param,
                         var_param_history=var_param_history,
                         value_history=value_history)
    if bound_w2 not in [False, None]:
        if bound_w2 is True:
            n_samples = 1000000
        else:
            n_samples = bound_w2
        with Timer('Computing CUBO and ELBO'):
            model_param_samples, log_weights = \
                get_samples_and_log_weights(logdensity, var_family, opt_param,
                                            n_samples)
            var_dist_cov = var_family.mean_and_cov(opt_param)[1]
            other_results.update(all_bounds(log_weights,
                                            model_param_samples,
                                            q_var=var_dist_cov,
                                            log_norm_bound=elbo))
        if verbose:
            print('using {} samples to compute bounds'.format(n_samples))
            print_bounds(other_results)
    if plot_contours:
        plot_approx_and_exact_contours(logdensity, var_family, opt_param,
                                       **contour_kws)
    if use_psis:
        other_results['psis_results'], _, _ = \
            improve_with_psis(logdensity, var_family, opt_param, n_samples,
                              true_mean, true_cov, verbose=verbose)
    return accuracy_results, other_results


def run_experiment(logdensity, var_family, init_param, true_mean, true_cov,
                   kl_n_samples=100, chivi_n_samples=500,
                   alpha=2, **kwargs):
    klvi = black_box_klvi(var_family, logdensity, kl_n_samples)
    chivi = black_box_chivi(alpha, var_family, logdensity, chivi_n_samples)
    dim = true_mean.size
    plot_contours = dim == 2
    if plot_contours:
        plot_approx_and_exact_contours(logdensity, var_family, init_param,
                                       **kwargs.get('contour_kws', dict()))

    print('Running KLVI...', flush=True)
    kl_results, other_kl_results = _optimize_and_check_results(
        logdensity, var_family, klvi, init_param,
        true_mean, true_cov, plot_contours, '-ELBO', **kwargs)
    kl_results['method'] = 'KLVI'
    print('Running CHIVI...', flush=True)
    elbo = other_kl_results['log_norm_bound']
    chivi_results, other_chivi_results = _optimize_and_check_results(
        logdensity, var_family, chivi, init_param, true_mean, true_cov,
        plot_contours, 'CUBO', elbo=elbo, **kwargs)
    chivi_results['method'] = 'CHIVI'
    return klvi, chivi, kl_results, chivi_results, other_kl_results, other_chivi_results