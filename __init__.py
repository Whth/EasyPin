import asyncio
import pathlib
import re
from datetime import datetime, timedelta
from typing import List, Callable, Dict

from colorama import Fore
from graia.ariadne import Ariadne
from graia.ariadne.event.lifecycle import ApplicationLaunch
from graia.ariadne.event.message import FriendMessage
from graia.ariadne.event.message import GroupMessage
from graia.ariadne.exception import AccountMuted
from graia.ariadne.message.chain import MessageChain
from graia.ariadne.message.element import Plain
from graia.scheduler import GraiaScheduler
from graia.scheduler.timers import crontabify

from modules.shared import (
    get_pwd,
    AbstractPlugin,
    NameSpaceNode,
    ExecutableNode,
    make_stdout_seq_string,
    EnumCMD,
    CmdBuilder,
    make_regex_part_from_enum,
    assemble_cmd_regex_parts,
)
from .analyze import Preprocessor, DEFAULT_PRESET, TO_DATETIME_PRESET, DATETIME_TO_CRONTAB_PRESET
from .task import ExtraPayload, crontab_to_time_stamp, crontab_to_datetime, delta_time_to_simple_stamp
from .task import TaskRegistry, ReminderTask, T_TASK

__all__ = ["EasyPin"]


class CMD(EnumCMD):
    task = ["tk", "tas"]
    set = ["s", "st"]
    list = ["l", "ls"]
    delete = ["d", "del"]
    clean = ["cls", "clr"]
    test = ["t", "te"]
    help = ["h"]
    info = ["inf"]
    rename = ["mv"]
    config = ["c", "cfg", "conf"]
    new = ["n", "ne"]


class External(object):
    SD_DEV = "StableDiffusionDev"
    CodeTalker = "CodeTalker"
    PicEval = "PicEval"


class EasyPin(AbstractPlugin):
    CONFIG_TASKS_SAVE_PATH = "tasks_save_path"

    CONFIG_ENABLE_CHECK = "enable_check"
    CONFIG_CHECK_CRONTAB = "crontab_check"

    CONFIG_CHECK_ADVANCE = "check_advance"
    CONFIG_TARGETS = "targets"
    DefaultConfig = {
        CONFIG_TASKS_SAVE_PATH: f"{get_pwd()}/cache/tasks.json",
        CONFIG_ENABLE_CHECK: 1,
        CONFIG_CHECK_CRONTAB: "7 7 * * * 0",
        CONFIG_CHECK_ADVANCE: 3,
        CONFIG_TARGETS: [],
    }

    @classmethod
    def get_plugin_name(cls) -> str:
        return "EasyPin"

    @classmethod
    def get_plugin_description(cls) -> str:
        return "a simple notify application"

    @classmethod
    def get_plugin_version(cls) -> str:
        return "0.1.1"

    @classmethod
    def get_plugin_author(cls) -> str:
        return "whth"

    def install(self):
        scheduler: GraiaScheduler = Ariadne.current().create(GraiaScheduler)
        to_datetime_processor = Preprocessor(TO_DATETIME_PRESET)

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
            cmds = {
                CMD.set.name: "用于设置任务，第一个参数为执行时间，第二个参数为任务名称，任务内容由引用的消息决定",
                CMD.list.name: "列出所有的定时任务",
                CMD.delete.name: "删除指定的任务",
                CMD.clean.name: "删除所有任务",
                CMD.test.name: "时间字符串解释测试",
                CMD.help.name: "展示这条信息",
            }

            stdout = "\n\n".join(f"{cmd} {help_string}" for cmd, help_string in cmds.items())
            return stdout

        def _task_list() -> str:
            """
            Returns a string representation of the task list.

            Returns:
                str: A string containing the task list, where each task is represented by its name and crontab schedule.
            """
            task_registry.remove_outdated_tasks()
            task_list = []

            for _task in task_registry.task_list:
                _task: T_TASK
                task_datetime = crontab_to_datetime(_task.crontab)
                delta_time: timedelta = task_datetime - datetime.now()

                task_list.append(
                    f"📌 {_task.task_name}\n"
                    f"\t⌛ {delta_time_to_simple_stamp(delta_time)}后发生\n"
                    f"\t⏰ {crontab_to_time_stamp(_task.crontab)}发生"
                )
            extra_string = "🫡\n"
            if self.config_registry.get_config(self.CONFIG_ENABLE_CHECK):
                extra_string += f"对每项任务会提前[{self.config_registry.get_config(self.CONFIG_CHECK_ADVANCE)}]天进行提醒"

            return make_stdout_seq_string(task_list, title="任务列表", extra=extra_string)

        def _clear() -> str:
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
            for _task in task_registry.task_list:
                if _task.task_name == task_name:
                    tasks_to_delete.append(_task)

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

        async def _task_content(task_name: str) -> str:
            """
            A function that gets the content of a task based on its name.

            Parameters:
                task_name (str): The name of the task.

            Returns:
                str: The content of the task if a match is found, otherwise "No Task Matched".
            """
            query = filter(lambda _task: _task.task_name == task_name, task_registry.task_list)
            if query:
                task_instance: T_TASK = list(query)[0]
                await task_instance.task_func()
                return f"Found {task_name}\n{task_instance.crontab}"
            return "No Task Matched"

        def _rename(index: int, new_name: str) -> str:
            """
            Renames a task in the task registry.

            Args:
                index (int): The index of the task in the task registry.
                new_name (str): The new name for the task.

            Returns:
                str: A message indicating the success of the renaming operation.
            """
            target_task = task_registry.task_list[index]
            target_task.task_name = new_name
            return f"Rename {target_task.task_name} to {target_task.crontab}"

        configurable = {
            self.CONFIG_ENABLE_CHECK,
            self.CONFIG_CHECK_ADVANCE,
            self.CONFIG_CHECK_CRONTAB,
        }
        builder = CmdBuilder(
            config_getter=self.config_registry.get_config,
            config_setter=self.config_registry.set_config,
        )
        tree = NameSpaceNode(
            **CMD.task.export(),
            required_permissions=self.required_permission,
            help_message=self.get_plugin_description(),
            children_node=[
                ExecutableNode(
                    **CMD.info.export(),
                    source=_task_content,
                ),
                ExecutableNode(
                    **CMD.help.export(),
                    source=_help,
                ),
                ExecutableNode(
                    **CMD.clean.export(),
                    source=_clear,
                ),
                ExecutableNode(
                    **CMD.list.export(),
                    source=_task_list,
                ),
                ExecutableNode(
                    **CMD.delete.export(),
                    source=_delete_task,
                ),
                ExecutableNode(
                    **CMD.test.export(),
                    source=_test_convert,
                ),
                ExecutableNode(
                    **CMD.rename.export(),
                    source=_rename,
                ),
                ExecutableNode(**CMD.new.export(), source=lambda *x: None),
                NameSpaceNode(
                    **CMD.config.export(),
                    help_message="配置相关命令",
                    children_node=[
                        ExecutableNode(
                            **CMD.list.export(),
                            source=builder.build_list_out_for(configurable),
                        ),
                        ExecutableNode(
                            **CMD.set.export(),
                            source=builder.build_group_setter_for(configurable),
                        ),
                    ],
                ),
            ],
        )

        self.root_namespace_node.add_node(tree)

        sd_dev = self.plugin_view.get(External.SD_DEV, None)
        code_talker = self.plugin_view.get(External.CodeTalker, None)
        pic_eval = self.plugin_view.get(External.PicEval, None)

        @self.receiver([FriendMessage, GroupMessage])
        async def pin_operator(app: Ariadne, message: FriendMessage | GroupMessage):
            """
            This function handles the pin operation based on the received message.
            Args:
                app (Ariadne): The Ariadne application instance.
                message (FriendMessage | GroupMessage): The message object received.
            """
            # Define the pattern for matching the command and arguments
            # Check if the message has an origin attribute

            if message.quote is None:
                return

            if isinstance(message, GroupMessage):
                target = message.sender.group
            elif isinstance(message, FriendMessage):
                target = message.sender
            else:
                raise ValueError("Unsupported message type")
            # Compile the regular expression pattern
            comp = re.compile(
                assemble_cmd_regex_parts(
                    [
                        make_regex_part_from_enum(CMD.task),
                        make_regex_part_from_enum(CMD.new),
                        r"(\S+)(?:\s+(.+)|(?:\s+)?$)",
                    ]
                )
            )

            # Find all matches of the pattern in the message
            matches = comp.findall(str(message.message_chain))

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
            title = match_groups[1]
            extra = ExtraPayload()
            origin_chain = str(message.quote.origin)
            origin_chain = origin_chain.replace("[图片]", "")
            if origin_chain and code_talker:
                summary = code_talker.chat(f"给出下面段话内容的分点总结：\n{origin_chain}")
                extra.messages.append("总结：\n" + summary) if summary else None

                if not title:
                    title: str = code_talker.chat(f"给下面这段话一个简短的标题（16字以内）：\n{origin_chain}")
                    title = title.strip('"')
                print(f"Grant summary: {summary}")
                print(f"Grant title: {title}")
            if pic_eval and sd_dev:
                porn_words = [
                    "nipples",
                    "pussy",
                    "censored",
                    "dick",
                    "porn",
                    "sex",
                    "nsfw",
                    "leotard",
                    "yuri",
                    "2girls",
                ]
                for i in range(7):
                    print(f"roll for pic-{i}")
                    rand_pic: str = pic_eval.rand_pic(quality=30)
                    try:
                        tags: Dict[str, float] = await sd_dev.interrogate(rand_pic)
                    except Exception as e:
                        print(f"Server error: {e}")
                        break
                    if any(porn_word in tags for porn_word in porn_words):
                        pathlib.Path(rand_pic).unlink()
                        print("Failed, delete porn pic")
                        continue
                    print("Accepted")
                    break
                else:
                    rand_pic = ""
                extra.images.append(pathlib.Path(rand_pic)) if rand_pic else None

            # Create a new ReminderTask object
            rem_task = ReminderTask(
                crontab=crontab,
                remind_content=[origin_id],
                target=target.id,
                task_name=title,
                extra=extra,
            )

            # Schedule the task using the scheduler
            scheduler.schedule(crontabify(crontab), cancelable=True)(await rem_task.make(app))
            # Register the task in the task registry
            task_registry.register_task(task=rem_task)

            # Run the last scheduled task
            active_msg = None
            try:
                active_msg = await app.send_message(
                    target=target,
                    quote=message.source,
                    message=MessageChain(
                        Plain(
                            f"📢新建任务:\n{rem_task.task_name}\n"
                            f"🏷️Crontab:\n{crontab}\n"
                            f"⌛剩余时间:\n{delta_time_to_simple_stamp(crontab_to_datetime(crontab)-datetime.now())}"
                        )
                    ),
                )

            except AccountMuted:
                print("AccountMuted is raised, skip send message")
            finally:
                print(f"Send message ==> Success={bool(active_msg)}")
                await scheduler.schedule_tasks[-1].run()

        async def check_task():
            """
            Checks if the scheduled tasks are still running.
            """
            if not self.config_registry.get_config(self.CONFIG_ENABLE_CHECK):
                print(f"{Fore.MAGENTA}Skip check task,Because it's disabled.{Fore.RESET}")
                return
            task_registry.remove_outdated_tasks()
            tasks = task_registry.tasks
            check_advance = self.config_registry.get_config(self.CONFIG_CHECK_ADVANCE)
            task_to_logging = []
            for crontab, sub_tasks in tasks.items():
                if (crontab_to_datetime(crontab) - datetime.now()).days <= check_advance:
                    for sub_task in sub_tasks.values():
                        string = (
                            f"{sub_task.task_name}\n"
                            f"\t🏷️{crontab_to_time_stamp(sub_task.crontab)}\n"
                            f"\t⌛{delta_time_to_simple_stamp(crontab_to_datetime(sub_task.crontab) - datetime.now())}"
                        )

                        task_to_logging.append(string)

            if task_to_logging:
                app = Ariadne.current()
                target_ids = self.config_registry.get_config(self.CONFIG_TARGETS)
                send_targets = await asyncio.gather(
                    *(
                        [app.get_friend(target_id) for target_id in target_ids]
                        + [app.get_group(target_id) for target_id in target_ids]
                    )
                )

                send_targets = filter(bool, send_targets)
                await asyncio.gather(
                    *[
                        app.send_message(target, make_stdout_seq_string(task_to_logging, title="任务检查", extra="🫡"))
                        for target in send_targets
                    ]
                )
                return
            print(f"No Task to logging, skip")

        @self.receiver(ApplicationLaunch)
        async def fetch_tasks():
            """
            Fetches tasks and schedules them using the scheduler.
            """

            from colorama import Fore

            stdout = ""
            # Print a message indicating that tasks are being fetched
            stdout += f"{Fore.YELLOW}------------------------------\nFetching tasks:{Fore.RESET}\n"

            # Iterate over each task in the task list
            for retrieved_task in task_registry.task_list:
                stdout += f"{Fore.MAGENTA}Retrieve Task {retrieved_task.crontab}|{retrieved_task.task_name}\n"
                # Schedule the task using the scheduler
                scheduler.schedule(crontabify(retrieved_task.crontab), cancelable=True)(
                    await retrieved_task.make(Ariadne.current())
                )

            stdout += (
                f"{Fore.YELLOW}Fetched {len(scheduler.schedule_tasks)} tasks\n"
                f"------------------------------\n{Fore.RESET}"
            )

            try:
                scheduler.schedule(timer=crontabify(self.config_registry.get_config(self.CONFIG_CHECK_CRONTAB)))(
                    check_task
                )
                stdout += (
                    f"{Fore.MAGENTA}Scheduled check task {self.config_registry.get_config(self.CONFIG_CHECK_CRONTAB)}\n"
                )
            except Exception as e:
                stdout += f"{Fore.RED}Failed to schedule check task\n" f"{e}\n{Fore.RESET}"
            finally:
                print(stdout)
            await scheduler.run()
