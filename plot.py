import os
import sys
import glob

import hydra
import numpy as np
import plotly.graph_objects as go
import plotly

import matplotlib.pyplot as plt
from dotmap import DotMap

import logging

log = logging.getLogger(__name__)

label_dict = {'t': 'Trajectory Based Deterministic',
              'd': 'One Step Deterministic',
              'p': 'One Step Probabilistic',
              'tp': 'Trajectory Based Probabilistic',
              'te': 'Trajectory Based Deterministic Ensemble',
              'de': 'One Step Deterministic Ensemble',
              'pe': 'One Step Probabilistic Ensemble',
              'tpe': 'Trajectory Based Probabilistic Ensemble'}
color_dict = {'t': 'r',
              'd': 'b',
              'p': 'g',
              'tp': 'y',
              'te': '#b53636',
              'de': '#3660b5',
              'pe': '#52b536',
              'tpe': '#b5af36'}
marker_dict = {'t': 's',
               'd': 'o',
               'p': 'D',
               'tp': 'p',
               'te': 's',
               'de': 'o',
               'pe': 'D',
               'tpe': 'p', }


def find_latest_checkpoint(cfg):
    '''
    Try to find the latest checkpoint in the log directory if cfg.checkpoint
    is not provided (usually through the command line).
    '''
    # same path as in save_log method, but with {} replaced to wildcard *
    checkpoint_paths = os.path.join(os.getcwd(),
                                    cfg.checkpoint_file.replace("{}", "*"))

    # use glob to find files (returned a list)
    files = glob.glob(checkpoint_paths)

    # If we cannot find one (empty file list), then do nothing and return
    if not files:
        return None

    # find the one with maximum last modified time (getmtime). Don't sort
    last_modified_file = max(files, key=os.path.getmtime)

    return last_modified_file


def plot_reacher(states, actions):
    ar = np.stack(states)
    l = np.shape(ar)[0]
    xs = np.arange(l)

    X = ar[:, -3]
    Y = ar[:, -2]
    Z = ar[:, -1]

    actions = np.stack(actions)

    fig = plotly.subplots.make_subplots(rows=2, cols=1,
                                        subplot_titles=("Position", "Action - Torques"),
                                        vertical_spacing=.15)  # go.Figure()
    fig.add_trace(go.Scatter(x=xs, y=X, name='X',
                             line=dict(color='firebrick', width=4)), row=1, col=1)
    fig.add_trace(go.Scatter(x=xs, y=Y, name='Y',
                             line=dict(color='royalblue', width=4)), row=1, col=1)
    fig.add_trace(go.Scatter(x=xs, y=Z, name='Z',
                             line=dict(color='green', width=4)), row=1, col=1)

    fig.add_trace(go.Scatter(x=xs, y=actions[:, 0], name='M1',
                             line=dict(color='firebrick', width=4)), row=2, col=1)
    fig.add_trace(go.Scatter(x=xs, y=actions[:, 1], name='M2',
                             line=dict(color='royalblue', width=4)), row=2, col=1)
    fig.add_trace(go.Scatter(x=xs, y=actions[:, 2], name='M3',
                             line=dict(color='green', width=4)), row=2, col=1)
    fig.add_trace(go.Scatter(x=xs, y=actions[:, 3], name='M4',
                             line=dict(color='orange', width=4)), row=2, col=1)
    fig.add_trace(go.Scatter(x=xs, y=actions[:, 4], name='M5',
                             line=dict(color='black', width=4)), row=2, col=1)

    fig.update_layout(title='Position of Reacher Task',
                      xaxis_title='Timestep',
                      yaxis_title='Angle (Degrees)',
                      plot_bgcolor='white',
                      xaxis=dict(
                          showline=True,
                          showgrid=False,
                          showticklabels=True, ),
                      yaxis=dict(
                          showline=True,
                          showgrid=False,
                          showticklabels=True, ),
                      )
    fig.show()


def generate_errorbar_traces(ys, xs=None, percentiles='66+95', color=None, name=None):
    if xs is None:
        xs = [list(range(len(y))) for y in ys]

    minX = min([len(x) for x in xs])

    xs = [x[:minX] for x in xs]
    ys = [y[:minX] for y in ys]

    assert all([(len(y) == len(ys[0])) for y in ys]), \
        'Y should be the same size for all traces'

    assert all([(x == xs[0]) for x in xs]), \
        'X should be the same for all traces'

    y = np.array(ys)

    def median_percentile(data, des_percentiles='66+95'):
        median = np.nanmedian(data, axis=0)
        out = np.array(list(map(int, des_percentiles.split("+"))))
        for i in range(out.size):
            assert 0 <= out[i] <= 100, 'Percentile must be >0 <100; instead is %f' % out[i]
        list_percentiles = np.empty((2 * out.size,), dtype=out.dtype)
        list_percentiles[0::2] = out  # Compute the percentile
        list_percentiles[1::2] = 100 - out  # Compute also the mirror percentile
        percentiles = np.nanpercentile(data, list_percentiles, axis=0)
        return [median, percentiles]

    out = median_percentile(y, des_percentiles=percentiles)
    ymed = out[0]
    # yavg = np.median(y, 0)

    err_traces = [
        dict(x=xs[0], y=ymed.tolist(), mode='lines', name=name, type='line', legendgroup=f"group-{name}",
             line=dict(color=color, width=4))]

    intensity = .3
    '''
    interval = scipy.stats.norm.interval(percentile/100, loc=y, scale=np.sqrt(variance))
    interval = np.nan_to_num(interval)  # Fix stupid case of norm.interval(0) returning nan
    '''

    for i, p_str in enumerate(percentiles.split("+")):
        p = int(p_str)
        high = out[1][2 * i, :]
        low = out[1][2 * i + 1, :]

        err_traces.append(dict(
            x=xs[0] + xs[0][::-1], type='line',
            y=(high).tolist() + (low).tolist()[::-1],
            fill='toself',
            fillcolor=(color[:-1] + str(f", {intensity})")).replace('rgb', 'rgba')
            if color is not None else None,
            line=dict(color='transparent'),
            legendgroup=f"group-{name}",
            showlegend=False,
            name=name + str(f"_std{p}") if name is not None else None,
        ), )
        intensity -= .1

    return err_traces, xs, ys


def plot_states(ground_truth, predictions, idx_plot=None, plot_avg=True, save_loc=None, show=True):
    """
    Plots the states given in predictions against the groundtruth. Predictions
    is a dictionary mapping model types to predictions
    """
    num = np.shape(ground_truth)[0]
    dx = np.shape(ground_truth)[1]
    if idx_plot is None:
        idx_plot = list(range(dx))

    for i in idx_plot:
        fig, ax = plt.subplots()
        gt = ground_truth[:, i]
        plt.title("Predictions on one dimension")
        plt.xlabel("Timestep")
        plt.ylabel("State Value")
        ax.spines['right'].set_visible(False)
        ax.spines['top'].set_visible(False)

        plt.plot(gt, c='k', label='Groundtruth')
        for key in predictions:
            # print(key)
            pred = predictions[key][:, i]
            # TODO: find a better way to do what the following line does
            chopped = np.maximum(np.minimum(pred, 3), -3)  # to keep it from messing up graphs when it diverges
            plt.plot(chopped, c=color_dict[key], label=label_dict[key], marker=marker_dict[key], markevery=50)

        plt.legend()

        if save_loc:
            plt.savefig(save_loc + "/state%d.pdf" % i)
        if show:
            plt.show()
        else:
            plt.close()

    if plot_avg:
        fig, ax = plt.subplots()
        gt = ground_truth[:, i]
        plt.title("Predictions Averaged")
        plt.xlabel("Timestep")
        plt.ylabel("Average State Value")
        ax.spines['right'].set_visible(False)
        ax.spines['top'].set_visible(False)

        gt = np.zeros(ground_truth[:, 0:1].shape)
        for i in idx_plot:
            gt = np.hstack((gt, ground_truth[:, i:i + 1]))
        gt_avg = np.average(gt[:, 1:], axis=1)
        plt.plot(gt_avg, c='k', label='Groundtruth')

        for key in predictions:
            pred = predictions[key]
            p = np.zeros(pred[:, 0:1].shape)
            for i in idx_plot:
                p = np.hstack((p, pred[:, i:i + 1]))
            p_avg = np.average(p[:, 1:], axis=1)
            plt.plot(p_avg, c=color_dict[key], label=label_dict[key], marker=marker_dict[key], markevery=50)
        # plt.ylim(-.5, 1.5)
        plt.legend()
        if save_loc:
            plt.savefig(save_loc + "/avg_states.pdf")
        if show:
            plt.show()
        else:
            plt.close()


def plot_loss(train_logs, test_logs, cfg, save_loc=None, show=False, title=None):
    """
    Plots the loss against the epoch number, designed to work with Nathan's DynamicsModel
    TODO: only integers on x-axis

    Parameters:
        logs: a list of lists of loss values, one list for each net in the model
        s: the string describing the model, ie 'd' or 'tpe'
    """
    fig = plotly.subplots.make_subplots(rows=1, cols=1,
                                        # subplot_titles=("Position", "Action - Torques"),
                                        vertical_spacing=.15)  # go.Figure()
    colors = [
        '#1f77b4',  # muted blue
        '#ff7f0e',  # safety orange
        '#2ca02c',  # cooked asparagus green
        '#d62728',  # brick red
        '#9467bd',  # muted purple
        '#8c564b',  # chestnut brown
        '#e377c2',  # raspberry yogurt pink
        '#7f7f7f',  # middle gray
        '#bcbd22',  # curry yellow-green
        '#17becf'  # blue-teal
    ]

    markers = [
        "cross-open-dot",
        "circle-open-dot",
        "x-open-dot",
        "triangle-up-open-dot",
        "y-down-open",
        "diamond-open-dot",
        "hourglass-open",
        "hash-open-dot",
        "star-open-dot",
        "square-open-dot",
    ]

    def add_line(fig, log, type, ind=-1):
        if ind == -1:
            name = type
        else:
            name = type + str(ind)
        if type == 'Test':
            fig.add_trace(go.Scatter(x=np.arange(len(log)).tolist(), y=log,
                                     name=name, legendgroup=type,
                                     line=dict(color=colors[ind], width=4),
                                     marker=dict(color=colors[ind], symbol=markers[ind], size=16)),
                          row=1, col=1)
        else:
            fig.add_trace(go.Scatter(x=np.arange(len(log)).tolist(), y=log,
                                     name=name, legendgroup=type,
                                     line=dict(color=colors[ind], width=4, dash='dash'),
                                     marker=dict(color=colors[ind], symbol=markers[ind], size=16)),
                          row=1, col=1)
        return fig

    if len(np.shape(train_logs)) > 1:
        # ENSEMBLE
        for i, (train, test) in enumerate(zip(train_logs, test_logs)):
            fig = add_line(fig, train, type="Train", ind=i)
            fig = add_line(fig, test, type="Test", ind=i)
    else:
        # BASE
        fig = add_line(fig, train_logs, type="Train", ind=-1)
        fig = add_line(fig, test_logs, type="Test", ind=-1)

    fig.update_layout(font=dict(
            family="Times New Roman, Times, serif",
            size=24,
            color="black"
        ),
        title='Training Plot ' + cfg.model.str,
        xaxis_title='Epoch',
        yaxis_title='Loss',
        plot_bgcolor='white',
        width=1000,
        height=1000,
        margin=dict(l=10, r=0, b=10),
        xaxis=dict(
            showline=True,
            showgrid=False,
            showticklabels=True, ),
        yaxis=dict(
            showline=True,
            showgrid=False,
            showticklabels=True, ),
    )
    if show: fig.show()
    fig.write_image(save_loc + ".png")

    # CODE FOR ADDING MARKERS EVERY FEW IN PLOTLY
    # DO NOT DELETE
    """
    def add_marker(err_traces, color=[], symbol=None, skip=None):
       mark_every = 100
       size = 85
       l = len(err_traces[0]['x'])
       if skip is not None:
           size_list = [0] * skip + [size] + [0] * (mark_every - 1 - skip)
       else:
           size_list = [size] + [0] * (mark_every - 1)
       repeat = int(l / mark_every)
       size_list = size_list * repeat
       line = err_traces[0]
       line['mode'] = 'lines+markers'
       line['marker'] = dict(
           color=line['line']['color'],
           size=size_list,
           symbol="x" if symbol is None else symbol,
           line=dict(width=4,
                     color='rgba(1,1,1,1)')
       )
       err_traces[0] = line
   return err_traces
   """


def plot_mse(MSEs, save_loc=None, show=True, log_scale=True, title=None):
    """
    Plots MSE graphs for the sequences given given

    Parameters:
    ------------
    MSEs: a dictionary mapping model type key to an array of MSEs
    """
    fig, ax = plt.subplots()
    title = title or "%s MSE for a variety of models" % ('Log ' if log_scale else '')
    plt.title(title)
    plt.xlabel("Timesteps")
    plt.ylabel('Mean Square Error')
    ax.spines['right'].set_visible(False)
    ax.spines['top'].set_visible(False)
    for key in MSEs:
        mse = MSEs[key]
        if log_scale:
            plt.semilogy(mse, color=color_dict[key], label=label_dict[key], marker=marker_dict[key], markevery=50)
        else:
            plt.plot(mse, color=color_dict[key], label=label_dict[key], marker=marker_dict[key], markevery=50)
    plt.legend()
    if save_loc:
        plt.savefig(save_loc)
    if show:
        plt.show()
    else:
        plt.close()


@hydra.main(config_path='config-plot.yaml')
def plot(cfg):
    pass

    # data = Data([new_trace1])
    #
    # plot_url = py.plot(data, filename='append plot', fileopt='append')


if __name__ == '__main__':
    sys.exit(plot())
