import re
from datetime import datetime
from datetime import timedelta
from typing import Callable, List, Optional, Sequence, Any, Union

from colorama import Fore

Procedure = Callable[[str], str]


class Preprocessor(object):
    """
    A class for preprocessing strings using a sequence of procedures.

    Attributes:
        _procedures (List[Procedure]): A list of procedures to be applied during the preprocessing.

    Methods:
        __init__(procedures: Optional[Sequence[Procedure]] = None):
            Initialize the Preprocessor with a list of procedures.
        process(string: str, logging: bool = False) -> Any:
            Apply the registered procedures to the input string.
        register_procedure(procedure: Procedure) -> None:
            Add a procedure to the list of registered procedures.
    """

    def __init__(self, procedures: Optional[Sequence[Procedure]] = None):
        self._procedures: List[Procedure] = []
        self._procedures.extend(procedures) if procedures else None

    def process(self, string: str, logging: bool = False) -> Any:
        """
        Process the given string using a series of procedures.

        Args:
            string (str): The input string to be processed.
            logging (bool, optional): Whether to enable logging.
            Defaults to False.

        Returns:
            Any: The processed string.
        """
        print(
            f"{Fore.MAGENTA}--------------------------------------------{Fore.RESET}\n"
            f"{Fore.YELLOW}Input: {string}{Fore.RESET}\n"
        ) if logging else None
        for procedure in self._procedures:
            temp = string
            string = procedure(temp)
            if logging:
                applied = temp != string
                stdout = (
                    f"{Fore.GREEN if applied else Fore.RED }With {procedure.__name__}, {'Not ' if not applied else ''}applied\n"
                    f"{string}"
                )
                print(stdout)
        print(f"{Fore.MAGENTA}--------------------------------------------{Fore.RESET}") if logging else None
        return string

    def register_procedure(self, procedure: Procedure) -> None:
        self._procedures.append(procedure)


def convert_day_period_to_abs_time(string: str) -> str:
    """
    Convert a string representation of a day period to absolute time.

    Args:
        string (str): The string representation of the day period.

    Returns:
        str: The converted string with the absolute time.

    Raises:
        ValueError: If the provided string does not match the expected format.

    Example:
        >>> convert_day_period_to_abs_time("黎明5点30分")
        "5时30分"
    """
    AM_hours_map = {
        "凌晨": [1, 0],
        "深夜": [3, 30],
        "黎明": [5, 30],
        "清晨": [6, 30],
        "早晨": [7, 30],
        "早上": [9, 30],
        "上午": [9, 30],
        "晌午": [10, 0],
        "午饭前": [11, 0],
        "午前": [11, 0],
        "正午": [12, 0],
        "中午": [12, 0],
    }
    PM_hours_map = {
        "午后": [13, 0],
        "午饭后": [13, 0],
        "下午": [15, 0],
        "黄昏": [16, 30],
        "傍晚": [17, 30],
        "晚上": [19, 30],
    }

    hour_names = ["点", "时"]
    min_names = ["分", "分钟"]

    am_reg = "|".join(AM_hours_map.keys())
    pm_reg = "|".join(PM_hours_map.keys())
    hour_name_reg = "|".join(hour_names)
    min_name_reg = "|".join(min_names)
    reg_exp = rf"(?:({am_reg})|({pm_reg}))(?:(\d+)(?:{hour_name_reg})(\d+)(?:{min_name_reg}))?"

    # Find all matches in the input string using the regular expression pattern
    matches = re.findall(pattern=reg_exp, string=string)

    # If no matches are found, return the original input string
    if not matches:
        return string
    # Extract the groups from the first match
    groups: Sequence[Union[str, Any]] = matches[0]

    if groups[0]:
        time_list = AM_hours_map.get(groups[0])
        offset = 0

    elif groups[1]:
        time_list = PM_hours_map.get(groups[1])
        offset = 12

    else:
        raise ValueError("should never arrive here!, since the reg expr will not let this happen")

    hour = int(groups[-2]) + offset if groups[-2] else time_list[0]
    minute = int(groups[-1]) if groups[-1] else time_list[-1]
    return re.sub(
        pattern=reg_exp,
        repl=f"{hour}时{minute}分",
        string=string,
        count=1,
    )


def convert_brief_time_to_num(string: str) -> str:
    """
    Convert a brief time string to a numerical representation.

    Args:
        string (str): The brief time string to be converted.

    Returns:
        str: The converted numerical representation of the brief time string.
    """
    min_map = {"半": 30, "整": 0, "1刻": 15, "2刻": 30, "3刻": 45}
    hour_names = ["点", "时", "小时"]

    min_reg = "|".join(min_map.keys())
    hour_reg = "|".join(hour_names)
    reg_exp = rf"(?:(?:{hour_reg})({min_reg})|(?:{hour_reg})(?:\s|$))"

    matches = re.findall(pattern=reg_exp, string=string)
    if not matches:
        return string

    # Extract the groups from the first match
    groups: str = matches[0]

    minute = min_map.get(groups, 0)

    return re.sub(
        pattern=reg_exp,
        repl=f"时{minute}分",
        string=string,
        count=1,
    )


def convert_brief_time_to_num_reversed(string: str) -> str:
    """
    Convert a brief time string to a numerical representation.

    Args:
        string (str): The brief time string to be converted.

    Returns:
        str: The converted numerical representation of the brief time string.
    """
    min_map = {"半个": 30, "半": 30}
    hour_names = ["点", "时", "小时", "钟"]

    min_reg = "|".join(min_map.keys())
    hour_reg = "|".join(hour_names)
    reg_exp = rf"({min_reg})(?:{hour_reg})"

    matches = re.findall(pattern=reg_exp, string=string)
    if not matches:
        return string

    # Extract the groups from the first match
    groups: Sequence[Union[str, Any]] = matches[0]

    minute = min_map.get(groups[0]) if groups[0] else 0

    return re.sub(
        pattern=reg_exp,
        repl=f"{minute}分",
        string=string,
        count=1,
    )


def chinese_to_arabic(string) -> int:
    """
    Converts a Chinese number string to an Arabic number.

    Args:
        string (str): The Chinese number string to be converted.

    Returns:
        int: The converted Arabic number.
    """
    string = string.strip()

    # Define a mapping of Chinese characters to their corresponding numeric values
    num_map = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}

    # Define a mapping of Chinese characters representing units to their corresponding values
    unit_map = {"十": 10, "百": 100, "千": 1000, "万": 10000, "亿": 100000000}

    result = 0
    temp = 0

    # Iterate through each character in the Chinese number string
    for char in string:
        if char in num_map:
            temp = num_map[char]
        elif char in unit_map:
            if char == "十" and temp == 0:
                temp = 1
            result += temp * unit_map[char]
            temp = 0

    result += temp
    return result


def replace_chinese_numbers(string) -> str:
    """
    Replaces Chinese numbers in a string with their Arabic equivalents.

    Args:
        string (str): The input string.

    Returns:
        str: The string with Chinese numbers replaced by their Arabic equivalents.
    """
    pattern = r"[零一二两三四五六七八九十百千万亿]+"  # pattern to match Chinese numbers
    matches = re.findall(pattern, string)  # find all matches of Chinese numbers in the string

    for match in matches:
        # convert the Chinese number to Arabic number
        arabic_num = chinese_to_arabic(match)
        # replace the Chinese number with the Arabic number in the string
        string = string.replace(match, str(arabic_num))

    return string


def convert_relative_to_abs(string: str) -> str:
    """
    Converts a relative month string to an absolute month string.

    Args:
        string: The input string containing the relative month.

    Returns:
        The input string with the relative month replaced by the absolute month.
    """

    # Define the names of time units
    hour_names = ["个小时", "小时", "钟", "时"]
    min_names = ["分", "分钟"]
    day_names = ["天", "日"]
    month_names = ["个月"]

    # Define prepositions used for matching
    prepositions = ["后", "之后"]

    # Create regular expressions patterns for matching relative month offsets, absolute month names,
    # and variations of month names
    hour_name_reg = "|".join(hour_names)
    min_name_reg = "|".join(min_names)
    day_name_reg = "|".join(day_names)
    month_name_reg = "|".join(month_names)
    preposition_reg = "|".join(prepositions)
    reg_exp = rf"(\d+)(?:({min_name_reg})|({hour_name_reg})|({day_name_reg})|({month_name_reg}))(?:{preposition_reg})"
    # Find all matches in the input string using the regular expression pattern
    matches = re.findall(pattern=reg_exp, string=string)

    # If no matches are found, return the original input string
    if not matches:
        return string
    # Extract the groups from the first match
    groups: Sequence[Union[str, Any]] = matches[0]
    offset = int(groups[0])
    # TODO add multiple offset calculation support
    if groups[1]:
        time_offset = timedelta(minutes=offset)
    elif groups[2]:
        time_offset = timedelta(hours=offset)
    elif groups[3]:
        time_offset = timedelta(days=offset)
    elif groups[4]:
        time_offset = timedelta(days=offset * 30)
    else:
        raise ValueError("should never arrive here!, since the reg expr will not let this happen")
    # Calculate the absolute values for month, day, hour, and minute

    abs_time = datetime.now() + time_offset
    # Replace the matched relative month string with the absolute month string
    return re.sub(
        pattern=reg_exp,
        repl=f"{abs_time.month}月{abs_time.day}日{abs_time.hour}点{abs_time.minute}分",
        string=string,
        count=1,
    )


def convert_relative_day_to_abs(string: str) -> str:
    """
    Converts a relative day string to an absolute day string.

    Args:
        string: The input string containing the relative day.

    Returns:
        The input string with the relative day replaced by the absolute day.

    Example:
        >>> convert_relative_day_to_abs("今天是明天")
        '9.19是明天'
    """

    # Map of weekdays in Chinese characters to their corresponding numerical value
    day_map = {"今": 0, "本": 0, "明": 1, "后": 2, "大后": 3}

    # List of variations of week names
    day_names = ["日", "天"]

    # Create regular expressions patterns for matching "this week" matches, "next week" matches,
    # week names, and weekdays

    day_name_reg = "|".join(day_names)
    day_reg = "|".join(day_map.keys())

    reg_exp = f"({day_reg})(?:{day_name_reg})"

    # Find all matches in the date string using the regular expression pattern
    matches = re.findall(pattern=reg_exp, string=string)

    # If no matches are found, return the original date string
    if not matches:
        return string

    # Extract the groups from the first match
    groups: Sequence[Union[str, Any]] = matches[0]

    # Get the numerical value of the weekday from the map
    offset = day_map[groups[0]]
    today = datetime.today().date()
    # Calculate the absolute date by adding the offset and the difference between the weekday
    # and the current weekday to the current date
    abs_date = today + timedelta(days=offset)

    # Replace the matched relative date string with the absolute date string
    return re.sub(
        pattern=reg_exp,
        repl=f"{abs_date.month}月{abs_date.day}日",
        string=string,
        count=1,
    )


def convert_relative_month_to_abs(string: str) -> str:
    """
    Converts a relative month string to an absolute month string.

    Args:
        string: The input string containing the relative month.

    Returns:
        The input string with the relative month replaced by the absolute month.

    """
    # Map of relative month offsets in Chinese characters to their corresponding numerical value
    relative_month_offset_map = {"这个": 0, "本": 0, "下": 1, "下个": 1}

    # List of variations of month names
    month_names = ["月", "月份"]

    # Create regular expressions patterns for matching relative month offsets, absolute month names,
    # and variations of month names
    offset_reg = "|".join(relative_month_offset_map.keys())

    name_reg = "|".join(month_names)
    reg_exp = f"(?:({offset_reg}))(?:{name_reg})"

    # Find all matches in the input string using the regular expression pattern
    matches = re.findall(pattern=reg_exp, string=string)

    # If no matches are found, return the original input string
    if not matches:
        return string

    # Extract the groups from the first match
    groups: Sequence[Union[str, Any]] = matches[0]
    # Get the numerical value of the relative month offset from the map
    offset = relative_month_offset_map.get(groups[0], 0)
    # Calculate the absolute month by adding the offset and the difference between the month
    # and the current month to the current month
    abs_month = datetime.today().month + offset

    # Replace the matched relative month string with the absolute month string
    return re.sub(
        pattern=reg_exp,
        repl=f"{abs_month}月",
        string=string,
        count=1,
    )


def convert_relative_weekday_to_absolute(string: str) -> str:
    """
    Converts a relative date string to an absolute date string.

    Args:
        string (str): The relative date string to convert.

    Returns:
        str: The converted absolute date string.
    """

    # Map of weekdays in Chinese characters to their corresponding numerical value
    weekday_map = {"末": 5, "一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6}

    # List of variations of "this week" matches
    this_week_matches = ["本", "本个", "这个", "现在这个"]

    # List of variations of "next week" matches
    next_week_matches = ["下", "下个", "接下来的"]

    # List of variations of week names
    week_names = ["周", "星期"]

    # Create regular expressions patterns for matching "this week" matches, "next week" matches,
    # week names, and weekdays
    this_week_reg = "|".join(this_week_matches)
    next_week_reg = "|".join(next_week_matches)
    week_name_reg = "|".join(week_names)
    weekday_reg = "|".join(weekday_map.keys())

    reg_exp = f"(?:({this_week_reg})|({next_week_reg}))?(?:{week_name_reg})({weekday_reg})"

    # Find all matches in the date string using the regular expression pattern
    matches = re.findall(pattern=reg_exp, string=string)

    # If no matches are found, return the original date string
    if not matches:
        return string

    # Extract the groups from the first match
    groups: Sequence[Union[str, Any]] = matches[0]

    offset = 0
    # If a match for "next week" is found, add 7 days to the offset
    if groups[1]:
        offset += 7

    # Get the numerical value of the weekday from the map
    weekday = weekday_map[groups[-1]]
    today = datetime.today().date()
    # Calculate the absolute date by adding the offset and the difference between the weekday
    # and the current weekday to the current date
    abs_date = today + timedelta(days=offset + weekday - today.weekday())

    # Replace the matched relative date string with the absolute date string
    return re.sub(
        pattern=reg_exp,
        repl=f"{abs_date.month}月{abs_date.day}日",
        string=string,
        count=1,
    )


def convert_date_to_crontab(string: str) -> str | None:
    """
    Convert a string representation of a cron expression into a crontab format.

    Args:
        string (str): The string representation of the cron expression.

    Returns:
        str | None: The converted crontab format string, or None if the input string does not match the expected pattern.
    """

    full_chinese_date_pattern = re.compile(r"^(?:(\d+)月)?(?:(\d+)[天日])?(?:(\d+)[点时:：.])?(\d+)?分?$")

    match = full_chinese_date_pattern.match(string)

    if match:
        now = datetime.now()
        month = match.group(1) or now.month
        day = match.group(2) or now.day
        hour = match.group(3) or now.hour
        minute = match.group(4) or now.minute

        return f"{minute} {hour} {day} {month} *"
    else:
        return None


def normalize_crontab(crontab_string: str | None) -> str | None:
    """
    Normalize a crontab string by replacing "60" with "0" in the minutes part, and "24" with "0" in the hours part.

    :param crontab_string: The crontab string to be normalized. Must be a string or None.
    :return: The normalized crontab string. Returns None if the input crontab string is None.
    :rtype: str or None
    """
    if not crontab_string:
        return

    parts = crontab_string.split()

    # 规范化分钟部分
    if parts[0] == "60":
        parts[0] = "0"
    # 规范化小时部分
    if parts[1] == "24":
        parts[1] = "0"

    return " ".join(parts)


# FIXME needs a bound check to prevent creating some hazordious crontab
TO_DATETIME_PRESET = [
    convert_brief_time_to_num,
    convert_brief_time_to_num_reversed,
    convert_relative_weekday_to_absolute,
    replace_chinese_numbers,
    convert_relative_to_abs,
    convert_day_period_to_abs_time,
    convert_relative_day_to_abs,
    convert_relative_month_to_abs,
]
DATETIME_TO_CRONTAB_PRESET = [
    convert_date_to_crontab,
    normalize_crontab,
]
DEFAULT_PRESET = TO_DATETIME_PRESET + DATETIME_TO_CRONTAB_PRESET


def is_crontab_expired(crontab_string: str) -> bool:
    """
    Check if a crontab schedule has expired.

    Args:
        crontab_string (str): The crontab schedule string.

    Returns:
        bool: True if the crontab schedule has not expired, False otherwise.
    """

    now = datetime.now()

    # split the crontab string into its individual components
    cron_parts = crontab_string.split()
    minute, hour, day, month, *_ = cron_parts

    # check if the current time matches the crontab schedule
    if (
        int(month) > now.month
        or (int(month) == now.month and int(day) > now.day)
        or (int(month) == now.month and int(day) == now.day and int(hour) > now.hour)
        or (int(month) == now.month and int(day) == now.day and int(hour) == now.hour and int(minute) > now.minute)
    ):
        return False

    return True


if __name__ == "__main__":
    shall_pass_tests = [
        "下个月3日下午2点半",
        "本月1日上午9点",
        "三个月之后",
        "三个月后",
        "今天十点半",
        "本周五晚上8点",
        "明天下午3点15分",
        "后天下午十二点",
        "中午12点",
        "晚上7点半",
        "下午4点整",
        "今天早上8点46分",
        "早上10点20分",
        "这个星期三下午8点",
        "今天17点",
        "晚上",
        "周六",
    ]
    shall_not_pass_tests = ["今年八月16日的阿纳", "之后的三天"]

    p = Preprocessor(DEFAULT_PRESET)
    result = [p.process(string, True) for string in shall_pass_tests]
    print(
        "\n---------------------------\n".join(
            f"{before}  =>  {after}" for before, after in zip(shall_pass_tests, result)
        )
    )
    print(result)
    print("\n".join([f"{tab} is expired: {is_crontab_expired(tab)}" for tab in result]))
    print("================================================")
    print(
        "\n---------------------------\n".join(
            f"{before}  =>  {after}"
            for before, after in zip(shall_not_pass_tests, [p.process(string) for string in shall_not_pass_tests])
        )
    )
