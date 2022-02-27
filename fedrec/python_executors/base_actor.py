from abc import ABC, abstractclassmethod, abstractmethod
from distutils.log import error
from typing import Dict
import os
import attr
import torch
from fedrec.preprocessor import PreProcessor
from fedrec.utilities import registry
from fedrec.utilities.logger import BaseLogger
from fedrec.utilities.random_state import Reproducible
from fedrec.data_models.state_tensors_model import StateTensors


class BaseActor(Reproducible, ABC):
    """Base Actor implements the core federated learning logic.
    It encapsulates the ML trainer to enable distributed training
    for the models defined in the standard setting.


    Attributes
    ----------
    worker_index : int
        The unique id alloted to the worker by the orchestrator
    persistent_storage : str
        The location to serialize and store the `WorkerState`
    is_mobile : bool
        Whether the worker represents a mobile device or not
    round_idx : int
        Number of local iterations finished
    """

    def __init__(self,
                 worker_index: int,
                 config: Dict,
                 logger: BaseLogger,
                 is_mobile: bool = True,
                 round_idx: int = 0):

        super().__init__(config["random"])
        self.round_idx = round_idx
        self.worker_index = worker_index
        self.is_mobile = is_mobile
        self.persistent_storage = (config["log_dir"]["PATH"]
                                   + "worker_id_"
                                   + str(self.worker_index))
        if not os.path.exists(self.persistent_storage):
            os.makedirs(self.persistent_storage)
        self.config = config
        self.logger = logger

        modelCls = registry.lookup('model', config["model"])
        self.model_preproc: PreProcessor = registry.instantiate(
            modelCls.Preproc,
            config["model"]['preproc'])
        self._model = None
        self._optimizer = None
        self.worker = None
        self.worker_funcs = {}

    @property
    def name(self):
        return self.__class__.__name__.lower()

    @property
    def optimizer(self):
        return None

    @abstractmethod
    def serialize(self):
        raise NotImplementedError

    @abstractclassmethod
    def load_worker(cls, *args, **kwargs):
        raise NotImplementedError

    @property
    def model(self):
        if self._model is not None:
            return self._model

        with self.model_random:
            # 1. Construct model
            self.model_preproc.load_data_description()
            self._model = registry.construct(
                'model', self.config['model'],
                preprocessor=self.model_preproc,
                unused_keys=('name', 'preproc')
            )
            if torch.cuda.is_available():
                self._model.cuda()
        return self._model

    def _get_model_params(self):
        """Get the current model parameters for the trainer .

        Returns
        -------
        Dict:
            A dict containing the model weights.
        """
        return StateTensors(
            storage=self.persistent_storage,
            worker_id=self.worker_index,
            tensors=self.model.cpu().state_dict(),
            round_idx=self.round_idx,
            tensor_type=self.name)

    def _get_optimizer_params(self):
        if self._optimizer is not None:
            return StateTensors(
                storage=self.persistent_storage,
                worker_id=self.worker_index,
                tensors=self.optimizer.state_dict(),
                round_idx=self.round_idx,
                tensor_type=self.name)
        else:
            raise ValueError("No optimizer found")

    def load_model(self, state_dict: StateTensors):
        """Update the model weights with weights.

        Parameters
        ----------
        weights : StateTensors
            The model weights to be loaded into the optimizer
        """
        self.model.load_state_dict(state_dict.get_torch_obj())

    def load_optimizer(self, state_dict: StateTensors):
        self.optimizer.load_state_dict(state_dict.get_torch_obj())

    def run(func_name, *args, **kwargs):
        pass
