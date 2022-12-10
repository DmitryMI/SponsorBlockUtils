import sys
import json
from subprocess import Popen, PIPE
from pathlib import Path
import os

DEFAULT_SPONSORBLOCK_CATEGORIES = ["Sponsor", "Intro"]
FFMPEG_LOG_LEVEL = "error"

def get_ffmpeg_filter_av_pair(index, time_start, time_end):
    pair = [
        f"[0:v]trim=start={time_start}:end={time_end}[{index}v];",
        f"[0:a]atrim=start={time_start}:end={time_end}[{index}a];"
    ];
    
    return pair[0] + " " + pair[1]

def get_ffmpeg_filter_concat(segments_number, output_path):
    cmd = ""
    for i in range(segments_number):
        cmd += f"[{i}v][{i}a]"

    cmd += f"concat=n={segments_number}:v=1:a=1[outv][outa] -map [outv] -map [outa] \"{output_path}\""
    return cmd

def get_video_duration(path):
    cmd = f"ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 \"{path}\""

    process = Popen(cmd, stdout=PIPE)
    (output, err) = process.communicate()
    exit_code = process.wait()

    output_str = output.decode("utf-8") 
    print("Video duration: ", output_str)
    duration = float(output)
    return duration

def get_video_chapters(input_path):
    process = Popen(f"ffprobe -i \"{input_path}\" -print_format json -show_chapters -loglevel error", stdout=PIPE)
    (output, err) = process.communicate()
    exit_code = process.wait()

    json_parsed = json.loads(output)

    if "chapters" in json_parsed:
        return json_parsed["chapters"]
    else:
        return None

def insert_name_suffix(path_input_str, suffix):
    path_input = Path(path_input_str)
    extension = path_input.suffix
    path_output_name = path_input_str.replace(extension, "")
    path_output_name += suffix+ extension
    return path_output_name

def get_output_path(path_input_str):
    return insert_name_suffix(path_input_str, "-SponsorBlocked")

def execute(cmd):
    popen = Popen(cmd, stdout=PIPE, universal_newlines=True)
    for stdout_line in iter(popen.stdout.readline, ""):
        yield stdout_line 
    popen.stdout.close()
    return_code = popen.wait()
    if return_code:
        raise Exception()

def ffmpeg_filter_complex(path_input, path_output, segments):
    cmd = f"ffmpeg -loglevel {FFMPEG_LOG_LEVEL} -i \"{path_input}\" -filter_complex \""

    for i, segment in enumerate(segments):
        cmd += get_ffmpeg_filter_av_pair(i,segment[0], segment[1]) + " "
    
    cmd += "\"" + get_ffmpeg_filter_concat(len(segments), path_output)

    print(cmd)

    for line in execute(cmd):
        print(line, end="")

def get_ffmpeg_segment_seeker(path_input, segment):

    time_start = segment[0]
    time_end = segment[1]

    if segment[0] == 0:
         return f"-to {time_end} -i \"{path_input}\""
    else:
        return f"-ss {time_start} -to {time_end} -i \"{path_input}\""

def get_ffmpeg_input_map(path_input, index):
    part_path = insert_name_suffix(path_input, f"-part{index}")
    return f"-map {index}:v -map {index}:a -c copy \"{part_path}\""

def get_ffmpeg_concat(path_input, path_output):
    list_path = path_input + ".list.txt"
    return f"ffmpeg -loglevel {FFMPEG_LOG_LEVEL} -y -safe 0 -f concat -i \"{list_path}\" -c copy \"{path_output}\""

def create_concat_list(path_input, segments_number):
     list_path = path_input + ".list.txt"
     with open(list_path, "w") as f:
         for i in range(segments_number):
             part_path = insert_name_suffix(path_input, f"-part{i}")
             part_path = part_path.replace("\\", "/")
             line = f"file {part_path}\n"
             f.write(line)

def delete_concat_list(path_input):
    list_path = path_input + ".list.txt"
    os.remove(list_path)

def delete_part_files(path_input, segments_number):
    for i in range(segments_number):
        part_path = insert_name_suffix(path_input, f"-part{i}")
        os.remove(part_path)

def ffmpeg_split_and_concat(path_input, path_output, segments):

    cmd_split = f"ffmpeg -loglevel {FFMPEG_LOG_LEVEL} -y "
    for i, segment in enumerate(segments):
        cmd_split += get_ffmpeg_segment_seeker(path_input, segment) + " "

    for i, segment in enumerate(segments):
        cmd_split += get_ffmpeg_input_map(path_input, i) + " "

    for line in execute(cmd_split):
        print(line, end="")

    create_concat_list(path_input, len(segments))

    cmd_concat = get_ffmpeg_concat(path_input, path_output)
    print(cmd_concat)
    for line in execute(cmd_concat):
        print(line, end="")

    delete_concat_list(path_input)
    delete_part_files(path_input, len(segments))

input_path = sys.argv[1]
print(input_path)

if not os.path.isfile(input_path):
    print(f"File {input_path} does not exist!")
    quit(-1)

chapters = get_video_chapters(input_path)
if chapters is None:
    print("Chapters not defined, nothing to do.")
    quit(0)

segments = []

timestamp = 0.0

sponsorblock_categories = DEFAULT_SPONSORBLOCK_CATEGORIES

for chapter in chapters:
    chapter_tags = chapter["tags"]
    chapter_title = chapter_tags["title"]
    chapter_start_time_str = chapter["start_time"]
    chapter_end_time_str = chapter["end_time"]

    if "[SponsorBlock]" not in chapter_title:
        continue

    chapter_category = chapter_title.replace("[SponsorBlock]: ", "")

    for sponsorblock_category in sponsorblock_categories:
        if sponsorblock_category in chapter_category:
            print(chapter_title, chapter_start_time_str, chapter_end_time_str)
            segments.append((timestamp, float(chapter_start_time_str)))
            timestamp = float(chapter_end_time_str)

duration = get_video_duration(input_path)
segments.append((timestamp, duration))

segments_refined = []

for segment in segments:
    segment_duration = segment[1] - segment[0]
    
    print(f"{segment}. Duration: {segment_duration}")
    if segment_duration != 0:
        segments_refined.append(segment)
    
if not segments_refined:
    print("SponsorBlock chapters not found, nothing to do")
    quit(0)

output_path = get_output_path(input_path)
print("Output path: ", output_path)
ffmpeg_split_and_concat(input_path, output_path, segments_refined)