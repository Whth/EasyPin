import os
import re
from typing import List, Callable

from modules.plugin_base import AbstractPlugin

__all__ = ["EasyPin"]


class EasyPin(AbstractPlugin):
    __TASK_CMD = "task"
    __TASK_SET_CMD = "new"
    __TASK_LIST_CMD = "list"
    __TASK_DELETE_CMD = "delete"
    __TASK_CLEAN_CMD = "clean"
    __TASK_TEST_CMD = "abd"
    __TASK_HELP_CMD = "help"

    CONFIG_TASKS_SAVE_PATH = "tasks_save_path"

    def _get_config_parent_dir(self) -> str:
        return os.path.abspath(os.path.dirname(__file__))

    @classmethod
    def get_plugin_name(cls) -> str:
        return "EasyPin"

    @classmethod
    def get_plugin_description(cls) -> str:
        return "a simple notify application"

    @classmethod
    def get_plugin_version(cls) -> str:
        return "0.0.3"

    @classmethod
    def get_plugin_author(cls) -> str:
        return "whth"

    def __register_all_config(self):
        self._config_registry.register_config(
            self.CONFIG_TASKS_SAVE_PATH, f"{self._get_config_parent_dir()}/cache/tasks.json"
        )

    def install(self):
        from graia.scheduler import GraiaScheduler
        from graia.scheduler.timers import crontabify
        from graia.ariadne.event.message import GroupMessage
        from graia.ariadne.event.lifecycle import ApplicationLaunch
        from modules.cmd import RequiredPermission, NameSpaceNode, ExecutableNode
        from modules.auth.resources import required_perm_generator
        from modules.auth.permissions import Permission, PermissionCode
        from graia.ariadne import Ariadne
        from graia.ariadne.model import Group
        from .analyze import Preprocessor, DEFAULT_PRESET, TO_DATETIME_PRESET, DATETIME_TO_CRONTAB_PRESET
        from .task import TaskRegistry, ReminderTask, T_TASK

        self.__register_all_config()
        self._config_registry.load_config()

        scheduler: GraiaScheduler = Ariadne.current().create(GraiaScheduler)
        to_datetime_processor = Preprocessor(TO_DATETIME_PRESET)
        datetime_to_crontab_processor = Preprocessor(DATETIME_TO_CRONTAB_PRESET)
        full_processor = Preprocessor(DEFAULT_PRESET)
        task_registry = TaskRegistry(self._config_registry.get_config(self.CONFIG_TASKS_SAVE_PATH), ReminderTask)

        def _test_convert(string: str) -> str:
            """
            Convert the given string to a datetime using the to_datetime_processor.

            Args:
                string (str): The string to be converted.

            Returns:
                str: The converted datetime string.
            """
            return to_datetime_processor.process(string)

        def _help() -> str:
            """
            Returns a string containing help information for the available commands.

            :return: A string containing help information for the available commands.
            :rtype: str
            """
            cmds = [
                self.__TASK_SET_CMD,
                self.__TASK_LIST_CMD,
                self.__TASK_DELETE_CMD,
                self.__TASK_TEST_CMD,
                self.__TASK_HELP_CMD,
            ]
            help_strings = ["用于设置任务，第一个参数为执行时间，第二个参数为任务名称，任务内容由引用的消息决定", "列举出所有的定时任务", "删除指定的任务", "时间字符串解释测试", "展示这条信息"]
            stdout = "\n\n".join(f"{cmd} {help_string}" for cmd, help_string in zip(cmds, help_strings))
            return stdout

        def _task_list() -> str:
            """
            Returns a string representation of the task list.

            Returns:
                str: A string containing the task list, where each task is represented by its name and crontab schedule.
            """
            task_registry.remove_outdated_tasks()
            temp_string = "Task List:\n"
            for crontab, tasks in task_registry.tasks.items():
                for name, _task in tasks.items():
                    _task: T_TASK
                    temp_string += f"{_task.task_name} | {_task.crontab}\n"
            return temp_string

        def _clean() -> str:
            """
            Cleans all scheduled tasks and removes them from the task registry.

            Returns:
                str: A message indicating the number of tasks cleaned.
            """
            clean_task_ct = 0
            for scheduled_task in scheduler.schedule_tasks:
                if not scheduled_task.stopped:
                    scheduled_task.stop()
                    scheduled_task.stop_gen_interval()
                    clean_task_ct += 1
            task_registry.remove_all_task()
            scheduler.stop()
            return f"Cleaned {clean_task_ct} Tasks in total"

        def _delete_task(task_name: str) -> str:
            """
            Deletes tasks with the given task_name.

            Args:
                task_name (str): The name of the task to delete.

            Returns:
                str: A message indicating the result of the deletion.
            """
            # Find tasks to delete
            tasks_to_delete: List[T_TASK] = []
            for task in task_registry.task_list:
                if task.task_name == task_name:
                    tasks_to_delete.append(task)

            # Return if no tasks found
            if len(tasks_to_delete) == 0:
                return f"Task {task_name} not Found!"

            # Get task functions to delete
            task_funcs_to_delete: List[Callable] = [_task.task_func for _task in tasks_to_delete]

            # Stop scheduler tasks associated with the task functions
            for sche_task in scheduler.schedule_tasks:
                if sche_task.target in task_funcs_to_delete:
                    print(f"stop task {sche_task.target}")
                    sche_task.stop()
                    sche_task.stop_gen_interval()

            # Remove tasks from the task registry
            task_registry.remove_task(task_name)

            # Return a deletion message
            return f"Delete {len(tasks_to_delete)} Tasks"

        su_perm = Permission(id=PermissionCode.SuperPermission.value, name=self.get_plugin_name())
        req_perm: RequiredPermission = required_perm_generator(
            target_resource_name=self.get_plugin_name(), super_permissions=[su_perm]
        )
        tree = NameSpaceNode(
            name=self.__TASK_CMD,
            required_permissions=req_perm,
            help_message=self.get_plugin_description(),
            children_node=[
                ExecutableNode(
                    name=self.__TASK_HELP_CMD,
                    source=_help,
                    help_message=_help.__doc__,
                ),
                ExecutableNode(
                    name=self.__TASK_CLEAN_CMD,
                    source=_clean,
                    help_message=_clean.__doc__,
                ),
                ExecutableNode(
                    name=self.__TASK_LIST_CMD,
                    source=_task_list,
                    help_message=_task_list.__doc__,
                ),
                ExecutableNode(
                    name=self.__TASK_DELETE_CMD,
                    source=_delete_task,
                    help_message=_delete_task.__doc__,
                ),
                ExecutableNode(
                    name=self.__TASK_TEST_CMD,
                    source=_test_convert,
                    help_message=_test_convert.__doc__,
                ),
            ],
        )
        self._auth_manager.add_perm_from_req(req_perm)
        self._root_namespace_node.add_node(tree)

        @self.receiver(GroupMessage)
        async def pin_operator(app: Ariadne, group: Group, message: GroupMessage):
            """
            Asynchronous pin operator function that receives a GroupMessage object and performs various operations based on the command and arguments provided.

            Args:
                group (Group): The Group object representing the group where the message was sent.
                message (GroupMessage): The GroupMessage object representing the message received.

            Returns:
                None

            Raises:
                None
            """
            # Define the pattern for matching the command and arguments
            pat = rf"{self.__TASK_CMD}\s+{self.__TASK_SET_CMD}\s+(\S+)(?:\s+(.+)|(?:\s+)?$)"

            # Check if the message has an origin attribute
            if not hasattr(message.quote, "origin"):
                print("no origin, not accepted")
                return

            # Compile the regular expression pattern
            comp = re.compile(pat)

            # Find all matches of the pattern in the message
            matches = re.findall(comp, str(message.message_chain))

            # If no matches are found, return
            if not matches:
                print("reg matches not accepted")
                return

            # Get the first match group
            match_groups = matches[0]

            # Get the origin id from the message quote
            origin_id = message.quote.id

            # Process the match group and add "0" at the end
            crontab = full_processor.process(match_groups[0], True) + " 0"

            # Create a new ReminderTask object
            task = ReminderTask(
                crontab=crontab,
                remind_content=[origin_id],
                target=group.id,
                task_name=match_groups[1] if match_groups[1] else None,
            )

            # Register the task in the task registry
            task_registry.register_task(task=task)

            # Save the tasks in the task registry
            task_registry.save_tasks()

            # Send a message to the group with the details of the scheduled task
            await app.send_message(group, f"Schedule new task:\n {task.task_name} | {crontab}")

            # Schedule the task using the scheduler
            scheduler.schedule(crontabify(crontab), cancelable=True)(await task.make(app))

            # Run the last scheduled task
            await scheduler.schedule_tasks[-1].run()

        @self.receiver(ApplicationLaunch)
        async def fetch_tasks():
            """
            Fetches tasks and schedules them using the scheduler.
            """

            from colorama import Fore

            # Print a message indicating that tasks are being fetched
            print(f"{Fore.YELLOW}------------------------------\nFetching tasks:{Fore.RESET}")

            # Iterate over each task in the task list
            for task in task_registry.task_list:
                print(f"{Fore.MAGENTA}Retrieve Task {task.crontab}|{task.task_name} ")
                # Schedule the task using the scheduler
                scheduler.schedule(crontabify(task.crontab), cancelable=True)(await task.make(Ariadne.current()))

            print(
                f"{Fore.YELLOW}Fetched {len(scheduler.schedule_tasks)} tasks\n"
                f"------------------------------\n{Fore.RESET}"
            )
            await scheduler.run()
