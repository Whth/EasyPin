import datetime
import json
import pathlib
import warnings
from abc import abstractmethod
from typing import List, Any, Dict, TypeVar, Type, final, Optional, Callable

from colorama import Fore
from graia.ariadne import Ariadne
from graia.ariadne.event.message import MessageEvent
from graia.ariadne.message.chain import MessageChain
from graia.ariadne.message.element import Forward, ForwardNode, Face, Image
from graia.ariadne.model import Profile
from pydantic import BaseModel, FilePath

from .analyze import is_crontab_expired


class ExtraPayload(BaseModel):
    messages: List[str] = []
    images: List[FilePath] = []
    chains: List[MessageChain] = []


class Task:
    """
    A base class for tasks.

    Attributes:
        task_name (str): The name of the task.
        crontab (str): The crontab expression for scheduling the task.

    Methods:
        __init__(task_name: str, crontab: str):
            Initialize the Task with a task name and a crontab expression.
        make(app: Ariadne) -> Any:
            Abstract method to be implemented by subclasses. Perform the task.
        as_dict() -> Dict:
            Return a dictionary representation of the task.
        _as_dict() -> Dict:
            Abstract method to be implemented by subclasses. Return a dictionary representation of the task-specific data.
    """

    def __init__(self, task_name: str, crontab: str):
        self.task_name: str = task_name
        self.crontab: str = crontab
        self._task_func: Optional[Callable] = None

    @final
    @property
    def task_func(self) -> Optional[Callable]:
        return self._task_func

    @abstractmethod
    async def make(self, app: Ariadne) -> Any:
        pass

    @final
    def as_dict(self) -> Dict:
        temp: Dict = {"task_name": self.task_name, "crontab": self.crontab}
        temp.update(self._as_dict())
        return temp

    @abstractmethod
    def _as_dict(self) -> Dict:
        pass


class ReminderTask(Task):
    """
    A class representing a reminder task.

    Attributes:
        task_name (str): The name of the task.
        crontab (str): The crontab expression for scheduling the task.
        remind_content (List[int]): The list of message IDs to be sent as reminders.
        target (int): The target group ID to send the reminders to.

    Methods:
        __init__(task_name: str, crontab: str, remind_content: List[int], target: int):
            Initialize the ReminderTask with a task name, crontab expression, remind content, and target.
        make(app: Ariadne):
            Perform the reminder task.
        _as_dict() -> Dict:
            Return a dictionary representation of the ReminderTask.
    """

    def __init__(
        self,
        crontab: str,
        remind_content: List[int] | List[str],
        target: int,
        task_name: Optional[str] = None,
        extra: Optional[ExtraPayload] = None,
    ):
        if not task_name:
            time_stamp = datetime.datetime.now().strftime("%Y-%m-%d-%H:%M:%S")
            task_name = f"{self.__class__.__name__}-{time_stamp}"
        super().__init__(task_name, crontab)
        self.target: int = target
        self._content_id_list: Optional[List[int]] = None
        if all(isinstance(item, int) for item in remind_content):
            self._content_id_list = remind_content
        elif all(isinstance(item, str) for item in remind_content):
            self.remind_content: List[str] = remind_content
        else:
            raise ValueError("remind_content must be a list of int or a list of str.")
        self.extra: ExtraPayload = extra

    async def retrieve_task_data(self, app: Ariadne, content_id_list: List[int]) -> List[str]:
        temp: List[str] = []
        for msg_id in content_id_list:
            msg_event: MessageEvent = await app.get_message_from_id(msg_id, self.target)
            temp.append(msg_event.message_chain.as_persistent_string())
        return temp

    async def make(self, app: Ariadne) -> Callable:
        """
        Perform the reminder task.

        Args:
            app (Ariadne): The Ariadne application object.

        Returns:
            Callable: An async function that sends the reminder messages.
        """
        if callable(self._task_func):
            warnings.warn("Task is already made")
            return self._task_func
        if self._content_id_list:
            self.remind_content: List[str] = await self.retrieve_task_data(app, self._content_id_list)
        profile: Profile = await app.get_bot_profile()
        nodes = [
            ForwardNode(
                app.account, time=datetime.datetime.now(), message=MessageChain(self.task_name), name=profile.nickname
            )
        ]
        for per_string in self.remind_content:
            chain = MessageChain.from_persistent_string(per_string)

            nodes.append(
                ForwardNode(
                    app.account,
                    time=datetime.datetime.now(),
                    message=chain,
                    name=profile.nickname,
                )
            )
        if self.extra:
            for chain in self.extra.chains:
                nodes.append(
                    ForwardNode(
                        app.account,
                        time=datetime.datetime.now(),
                        message=chain,
                        name=profile.nickname,
                    )
                )
            for message in self.extra.messages:
                nodes.append(
                    ForwardNode(
                        app.account,
                        time=datetime.datetime.now(),
                        message=MessageChain(message),
                        name=profile.nickname,
                    )
                )
            for image_path in self.extra.images:
                nodes.append(
                    ForwardNode(
                        app.account,
                        time=datetime.datetime.now(),
                        message=MessageChain(Image(path=image_path)),
                        name=profile.nickname,
                    )
                )

        nodes.append(
            ForwardNode(
                app.account,
                time=datetime.datetime.now(),
                message=MessageChain("不要忘了哦") + Face(name="玫瑰"),
                name=profile.nickname,
            )
        )

        async def _():
            try:
                await app.send_group_message(self.target, Forward(nodes))
            except ValueError:
                await app.send_friend_message(self.target, Forward(nodes))

        self._task_func = _
        return self._task_func

    def _as_dict(self) -> Dict:
        """
        Return a dictionary representation of the ReminderTask.

        Returns:
            Dict: The dictionary representation of the ReminderTask.
        """
        return {"remind_content": self.remind_content, "target": self.target}


T_TASK = TypeVar("T_TASK", bound=Task)


class TaskRegistry(object):
    def __init__(
        self,
        save_path: str,
        task_type: Type[T_TASK],
    ):
        self._save_path: str = save_path
        self._task_type: Type[T_TASK] = task_type
        self._tasks: Dict[str, Dict[str, T_TASK]] = {}
        if pathlib.Path(save_path).exists():
            self.load_tasks()
            self.remove_outdated_tasks()

    @property
    def tasks(self) -> Dict[str, Dict[str, T_TASK]]:
        """
        Return the dictionary of tasks.

        :return: A dictionary containing tasks.
        :rtype: Dict[str, Dict[str, T_TASK]]
        """
        return self._tasks

    @property
    def task_list(self) -> List[T_TASK]:
        """
        Returns a list of all tasks in the task list.

        Parameters:
            None

        Returns:
            List[T_TASK]: A list of all tasks in the task list.
        """
        task_list: List[T_TASK] = []
        for tasks in self._tasks.values():
            for task in tasks.values():
                task: T_TASK
                task_list.append(task)
        return task_list

    def register_task(self, task: T_TASK, with_save: bool = True) -> None:
        """
        Register a task in the task manager.

        Args:
            task (T_TASK): The task to register.
            with_save (bool, optional): Whether to save the tasks. Defaults to True.

        Raises:
            TypeError: If the task is not of the correct type.

        Returns:
            None
        """
        if not isinstance(task, self._task_type):
            raise TypeError(f"Task {task} is not of type {self._task_type}")
        if task.crontab in self._tasks:
            self._tasks[task.crontab][task.task_name] = task
        else:
            self._tasks[task.crontab] = {task.task_name: task}
        self.save_tasks() if with_save else None

    def remove_outdated_tasks(self):
        """
        Remove outdated tasks from the task dictionary.

        Parameters:
            None.

        Returns:
            None.
        """
        Unexpired_tasks: Dict[str, Dict[str, T_TASK]] = {}
        for crontab, tasks in self._tasks.items():
            if not is_crontab_expired(crontab):
                Unexpired_tasks[crontab] = tasks
        self._tasks = Unexpired_tasks

    def load_tasks(self):
        """
        Load tasks from a file.

        This function reads the tasks from a file specified by `self._save_path` and populates the `_tasks` dictionary
        based on the contents of the file. The file is expected to be in JSON format.

        Parameters:
            self (obj): The current instance of the class.

        Returns:
            None
        """
        if not pathlib.Path(self._save_path).exists():
            return
        with open(self._save_path, "r", encoding="utf-8") as f:
            temp_dict: Dict[str, Dict[str, Dict[str, Any]]] = json.load(f)
        for crontab, tasks in temp_dict.items():
            self._tasks[crontab] = {}
            for task_name, task_data in tasks.items():
                self._tasks[crontab][task_name] = self._task_type(**task_data)

    def save_tasks(self):
        """
        Save the tasks to the specified file path.

        This function saves the tasks stored in the `_tasks` attribute to the file specified by `self._save_path`.
        The tasks are converted into a temporary dictionary structure, where each crontab is a key that maps to a dictionary of task names and their corresponding attributes.
        The temporary dictionary is then written to the file in JSON format.

        Parameters:
            None

        Returns:
            None
        """
        print(f"{Fore.MAGENTA}Saving tasks to {self._save_path}")
        pathlib.Path(self._save_path).parent.mkdir(parents=True, exist_ok=True)
        temp_dict: Dict[str, Dict[str, Dict[str, Any]]] = {}
        for crontab, tasks in self._tasks.items():
            temp_dict[crontab] = {}
            for task_name, task in tasks.items():
                task: T_TASK
                temp_dict[crontab][task_name] = task.as_dict()
        with open(self._save_path, "w", encoding="utf-8") as f:
            json.dump(temp_dict, f, ensure_ascii=False, indent=2)

    def remove_all_task(self):
        """
        Remove all tasks from the task list.
        """
        self._tasks.clear()

    def remove_task(self, target_info: str):
        """
        Remove a task from the internal task dictionary based on target_info.

        Args:
            target_info (str): The identifier of the task to be removed.
        """
        # Create a temporary dictionary to store the updated tasks
        temp_dict: Dict[str, Dict[str, T_TASK]] = {}

        # Iterate over the existing tasks
        for crontab, tasks in self._tasks.items():
            # Check if the current crontab matches the target_info
            if crontab == target_info:
                break

            # Create a new dictionary to store the tasks that will survive
            survived = {}

            # Iterate over the tasks in the current crontab
            for task_name, task in tasks.items():
                # Exclude the task with the target_info from the surviving tasks
                if task_name != target_info:
                    survived[task_name] = task

            # Add the surviving tasks to the temporary dictionary
            temp_dict[crontab] = survived

        # Clear the existing tasks dictionary
        self._tasks.clear()

        # Update the task dictionary with the temporary dictionary
        self._tasks.update(temp_dict)


def crontab_to_time_stamp(crontab: str) -> str:
    """
    Convert a crontab string to a timestamp.

    Args:
        crontab (str): The crontab string to be converted.

    Returns:
        int: The timestamp of the crontab.
    Examples:
        >>>crontab_to_time_stamp('0 15 6 11 * 0')
        11月6日15:00
    """

    # 创建datetime对象
    dt = datetime.datetime.strptime(crontab, "%M %H %d %m * %S")
    # 转换为时间戳并返回
    return dt.strftime("%m月%d日%H:%M")


def crontab_to_datetime(crontab: str) -> datetime.datetime:
    """
    Convert a crontab string to a datetime object.

    Args:
        crontab (str): The crontab string to be converted.

    Returns:
        datetime.datetime: The datetime object of the crontab.
    Examples:
        >>>crontab_to_datetime('0 15 6 11 * 0')
        datetime.datetime(2022, 11, 6, 15, 0)
    """
    return datetime.datetime.strptime(crontab + f" {datetime.datetime.now().year}", "%M %H %d %m * %S %Y")


def delta_time_to_simple_stamp(delta_time: datetime.timedelta) -> str:
    """
    Convert a timedelta object to a simple timestamp string.

    Args:
        delta_time (datetime.timedelta): The timedelta object to be converted.

    Returns:
        str: The simple timestamp string of the timedelta.
    Examples:
        >>>delta_time_to_simple_stamp(datetime.timedelta(minutes=2))
        00:02:00
    """

    temp = {"天": delta_time.days, "时": delta_time.seconds // 3600, "分": delta_time.seconds % 3600 % 60}
