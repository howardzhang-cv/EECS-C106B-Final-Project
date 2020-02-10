import numpy as np
from dotmap import DotMap

from timeit import default_timer as timer
import matplotlib.pyplot as plt

import torch
from torch.autograd import Variable
import torch.nn as nn
import torch.nn.functional as F
import torch.backends.cudnn as cudnn
import gym
from envs import *

import hydra
import logging

log = logging.getLogger(__name__)

class Net(nn.Module):
    """
    Deterministic Neural Network
    """

    def __init__(self, structure=[20, 100, 100, 1], tf=F.relu):
        """
        :param structure: layer sizes
        :param tf: nonlinearity function
        """
        super(Net, self).__init__()

        # TODO: parameteric NN
        fc = []
        self.n_layers = len(structure) - 1
        for i in range(self.n_layers):
            fc.append(nn.Linear(structure[i], structure[i+1]))
        # self.fc1 = nn.Linear(structure[0], structure[1])
        # # self.d1 = nn.Dropout()
        # self.fc2 = nn.Linear(structure[1], structure[2])
        # # self.d2 = nn.Dropout()
        # self.fc3 = nn.Linear(structure[2], structure[3])
        self.linears = nn.ModuleList(fc)
        self.tf = tf
        self._onGPU = False

    def forward(self, x):
        for i in range(self.n_layers-1):
            x = self.tf(self.linears[i](x))
        x = self.linears[self.n_layers-1](x)
        # x = self.tf(self.fc1(x))
        # # x = self.d1(x)
        # x = self.tf(self.fc2(x))
        # # x = self.d2(x)
        # x = self.fc3(x)
        return x

    def predict(self, x):
        """
        wrapper to/from numpy array
        :param x:
        :return:
        """
        if self._onGPU:
            pass
        else:
            return self.forward(Variable(torch.from_numpy(np.matrix(x)).float())).data.cpu().numpy()

class Prob_Loss(nn.Module):
    def __init__(self):
        super(Prob_Loss, self).__init__()

    def forward(self, inputs, targets):
        size = targets.size()[1]
        mean = inputs[:,:size]
        var = inputs[:,size:]
        diff = mean-targets
        mid = diff / var
        lg = torch.sum(torch.log(var))
        # print(lg)
        # print(diff.size())
        # print(mid.size())
        out = torch.trace(torch.mm(diff, mid.t())) + lg
        # print(out
        return out

class Ensemble:
    def __init__(self, structure=[20, 100, 100, 1], n=10):
        self.models = [Net(structure=structure) for _ in range(n)]
        self.n = n
        self.structure = structure

    def predict(self, x):
        predictions = np.array([model.predict(x) for model in self.models])
        return np.average(predictions, axis=1)

    def train(self, dataset, parameters=DotMap()):
        # Partitioning data
        partition_size = dataset.shape[1]//self.n
        partitions = [dataset[:,i*partition_size:(i+1)*partition_size] for i in range(n)]
        datasets = []
        for i in range(n):
            ds = []
            for j in range(n):
                if i==j:
                    continue
                ds.extend(partitions[j])
            datasets.append(ds)

        # Training
        for i in range(n):
            train_network(datasets[i], models[i], parameters=parameters)

def train_network(dataset, model, parameters=DotMap()):
    import torch.optim as optim
    from torch.utils.data.dataset import Dataset
    from torch.utils.data import DataLoader

    # This bit basically adds variables to the dotmap with default values
    p = DotMap()
    p.opt.n_epochs = parameters.opt.get('n_epochs', 10)
    p.opt.optimizer = optim.Adam
    p.opt.batch_size = parameters.opt.get('batch_size', 100)
    p.criterion = parameters.get("criterion", nn.MSELoss())
    p.learning_rate = parameters.get('learning_rate', 0.0001)
    p.useGPU = parameters.get('useGPU', False)
    p.verbosity = parameters.get('verbosity', 1)
    p.logs = parameters.get('logs', None)

    # Init logs
    if p.logs is None:
        logs = DotMap()
        logs.training_error = []
        logs.training_error_epoch = []
        logs.time = None
    else:
        logs = p.logs

    # Optimizer
    optimizer = p.opt.optimizer(model.parameters(), lr=p.learning_rate)

    # Lets cudnn autotuner find optimal algorithm for hardware
    cudnn.benchmark = True

    if p.useGPU:
        model.cuda()
        p.criterion.cuda()

    # Wrapper representing map-style PyTorch dataset
    class PytorchDataset(Dataset):
        def __init__(self, dataset):
            self.inputs = torch.from_numpy(dataset[0]).float()
            self.outputs = torch.from_numpy(dataset[1]).float()
            self.n_data = dataset[0].shape[0]
            self.n_inputs = dataset[0].shape[1]
            self.n_outputs = dataset[1].shape[1]

        def __getitem__(self, index):
            # print('\tcalling Dataset:__getitem__ @ idx=%d' % index)
            input = self.inputs[index]
            output = self.outputs[index]
            return input, output

        def __len__(self):
            # print('\tcalling Dataset:__len__')
            return self.n_data

    log.info('Training NN from dataset')

    # Puts it in PyTorch dataset form and then converts to DataLoader
    #
    # DataLoader is an iterable
    dataset = PytorchDataset(dataset=dataset)  # Using PyTorch
    loader = DataLoader(dataset, batch_size=p.opt.batch_size, shuffle=True)  ##shuffle=True #False
    # pin_memory=True
    # drop_last=False

    startTime = timer()
    if logs.time is None:
        logs.time = [0]

    print("Training for %d epochs" % p.opt.n_epochs)

    for epoch in range(p.opt.n_epochs):
        epoch_error = 0
        log.info("Epoch %d" % (epoch))
        for i, data in enumerate(loader, 0):
            if i % 100 == 0:
                print("    Batch %d" % i)
            # Load data
            # Variable is a wrapper for Tensors with autograd
            inputs, targets = data
            if p.useGPU:
                inputs = Variable(inputs.cuda())
                targets = Variable(targets.cuda())
            else:
                inputs = Variable(inputs)
                targets = Variable(targets)

            optimizer.zero_grad()
            outputs = model.forward(inputs)
            loss = p.criterion(outputs, targets)
            # print(loss)

            e = loss.item()
            logs.training_error.append(e)
            epoch_error += e
            # log.info('Iter %010d - %f ' % (epoch, e))
            loss.backward()
            optimizer.step()  # Does the update
            logs.time.append(timer() - logs.time[-1])
        logs.training_error_epoch.append(epoch_error)

    endTime = timer()
    log.info('Optimization completed in %f[s]' % (endTime - startTime))

    return model.cpu(), logs
