const MEMORY_STATE_PATH = "user://buckshot_memory_state.json"
const MEMORY_BRIDGE_VERSION = 1
var memory_known : Array[bool] = []
var memory_last_write_ms : int = 0
var memory_previous_sequence : Array[String] = []
var memory_live_options : Array[int] = [0]
var memory_pre_inverter_live_options : Array[int] = []
var memory_inverter_uncertain : bool = false

func _ready():
	set_process(true)
	MemoryResetKnown()


func _process(_delta):
	var now = Time.get_ticks_msec()
	if now - memory_last_write_ms >= 160:
		MemorySyncChanges()
		MemoryWriteState(true)


func _exit_tree():
	MemoryWriteState(false)


func MemoryResetKnown():
	memory_known = []
	for _shell in sequenceArray:
		memory_known.append(false)
	memory_previous_sequence = sequenceArray.duplicate()
	memory_live_options = [sequenceArray.count("live")]
	memory_pre_inverter_live_options = []
	memory_inverter_uncertain = false
	MemoryWriteState(true)


func MemoryUniqueSorted(values : Array[int]) -> Array[int]:
	var result : Array[int] = []
	for value in values:
		if value >= 0 && value <= sequenceArray.size() && value not in result:
			result.append(value)
	result.sort()
	return result


func MemorySyncChanges():
	if sequenceArray.size() < memory_previous_sequence.size():
		var removed_count = memory_previous_sequence.size() - sequenceArray.size()
		var removed_live = 0
		for i in range(removed_count):
			if memory_previous_sequence[i] == "live":
				removed_live += 1
		for _i in range(removed_count):
			if !memory_known.is_empty():
				memory_known.pop_front()
		if memory_inverter_uncertain:
			memory_live_options = [sequenceArray.count("live")]
		else:
			var shifted : Array[int] = []
			for value in memory_live_options:
				shifted.append(value - removed_live)
			memory_live_options = MemoryUniqueSorted(shifted)
		memory_pre_inverter_live_options = []
		memory_inverter_uncertain = false
	elif sequenceArray.size() > memory_previous_sequence.size():
		MemoryResetKnown()
		return
	elif (
		!sequenceArray.is_empty()
		&& !memory_previous_sequence.is_empty()
		&& sequenceArray[0] != memory_previous_sequence[0]
	):
		if !memory_known.is_empty() && memory_known[0]:
			var delta = -1 if memory_previous_sequence[0] == "live" else 1
			var adjusted : Array[int] = []
			for value in memory_live_options:
				adjusted.append(value + delta)
			memory_live_options = MemoryUniqueSorted(adjusted)
		elif memory_inverter_uncertain:
			memory_live_options = memory_pre_inverter_live_options.duplicate()
			memory_pre_inverter_live_options = []
			memory_inverter_uncertain = false
		else:
			memory_pre_inverter_live_options = memory_live_options.duplicate()
			var uncertain : Array[int] = []
			for value in memory_live_options:
				uncertain.append(value - 1)
				uncertain.append(value + 1)
			memory_live_options = MemoryUniqueSorted(uncertain)
			memory_inverter_uncertain = true
	while memory_known.size() > sequenceArray.size():
		memory_known.pop_front()
	while memory_known.size() < sequenceArray.size():
		memory_known.append(false)
	memory_previous_sequence = sequenceArray.duplicate()


func MemoryMarkKnown(index : int):
	MemorySyncChanges()
	if index >= 0 && index < memory_known.size():
		memory_known[index] = true
		if index == 0 && memory_inverter_uncertain:
			memory_live_options = [sequenceArray.count("live")]
			memory_pre_inverter_live_options = []
			memory_inverter_uncertain = false
		MemoryWriteState(true)


func MemoryWriteState(active : bool):
	memory_last_write_ms = Time.get_ticks_msec()
	var known_sequence : Array[String] = []
	var blank_options : Array[int] = []
	for i in range(sequenceArray.size()):
		if i < memory_known.size() && memory_known[i]:
			known_sequence.append(sequenceArray[i])
		else:
			known_sequence.append("unknown")
	for value in memory_live_options:
		blank_options.append(sequenceArray.size() - value)
	blank_options = MemoryUniqueSorted(blank_options)
	var payload = {
		"schema": MEMORY_BRIDGE_VERSION,
		"bridge": "Buckshot Memory",
		"mode": "singleplayer",
		"active": active,
		"tick": memory_last_write_ms,
		"remaining": sequenceArray.size(),
		"live_options": memory_live_options,
		"blank_options": blank_options,
		"known_sequence": known_sequence,
	}
	var file = FileAccess.open(MEMORY_STATE_PATH, FileAccess.WRITE)
	if file != null:
		file.store_string(JSON.stringify(payload))
