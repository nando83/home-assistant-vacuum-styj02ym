"""Support for the Xiaomi vacuum cleaner robot."""
import asyncio
from functools import partial
import logging

from miio import DeviceException, Vacuum # pylint: disable=import-error
import voluptuous as vol

from homeassistant.components.vacuum import (
	ATTR_CLEANED_AREA,
	DOMAIN,
	PLATFORM_SCHEMA,
	STATE_CLEANING,
	STATE_DOCKED,
	STATE_ERROR,
	STATE_IDLE,
	STATE_PAUSED,
	STATE_RETURNING,
	SUPPORT_BATTERY,
	SUPPORT_FAN_SPEED,
	SUPPORT_LOCATE,
	SUPPORT_PAUSE,
	SUPPORT_RETURN_HOME,
	SUPPORT_SEND_COMMAND,
	SUPPORT_START,
	SUPPORT_STATE,
	SUPPORT_STOP,
	# StateVacuumDevice,
	StateVacuumEntity,
)
from homeassistant.const import (
	ATTR_ENTITY_ID,
	CONF_HOST,
	CONF_NAME,
	CONF_TOKEN,
	STATE_OFF,
	STATE_ON,
)
import homeassistant.helpers.config_validation as cv

_LOGGER = logging.getLogger(__name__)

DEFAULT_NAME = "Xiaomi Vacuum cleaner STYJ02YM"
DATA_KEY = "vacuum.miio2"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
	{
		vol.Required(CONF_HOST): cv.string,
		vol.Required(CONF_TOKEN): vol.All(str, vol.Length(min=32, max=32)),
		vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
	},
	extra=vol.ALLOW_EXTRA,
)

VACUUM_SERVICE_SCHEMA = vol.Schema(
	{vol.Optional(ATTR_ENTITY_ID): cv.comp_entity_ids}
)
SERVICE_CLEAN_ZONE = "xiaomi_clean_zone"
SERVICE_CLEAN_POINT = "xiaomi_clean_point"
ATTR_ZONE_ARRAY = "zone"
ATTR_ZONE_REPEATER = "repeats"
ATTR_POINT = "point"
SERVICE_SCHEMA_CLEAN_ZONE = VACUUM_SERVICE_SCHEMA.extend(
	{
		vol.Required(ATTR_ZONE_ARRAY): vol.All(
			list,
			[
				vol.ExactSequence(
					[vol.Coerce(float), vol.Coerce(float), vol.Coerce(float), vol.Coerce(float)]
				)
			],
		),
		vol.Required(ATTR_ZONE_REPEATER): vol.All(
			vol.Coerce(int), vol.Clamp(min=1, max=3)
		),
	}
)
SERVICE_SCHEMA_CLEAN_POINT = VACUUM_SERVICE_SCHEMA.extend(
	{
		vol.Required(ATTR_POINT): vol.All(
			vol.ExactSequence(
				[vol.Coerce(float), vol.Coerce(float)]
			)
		)
	}
)
SERVICE_TO_METHOD = {
	SERVICE_CLEAN_ZONE: {
		"method": "async_clean_zone",
		"schema": SERVICE_SCHEMA_CLEAN_ZONE,
	},
	SERVICE_CLEAN_POINT: {
		"method": "async_clean_point",
		"schema": SERVICE_SCHEMA_CLEAN_POINT,
	}
}

FAN_SPEEDS = {"Silent": 0, "Standard": 1, "Medium": 2, "Turbo": 3}

SUPPORT_XIAOMI = (
	SUPPORT_STATE
	| SUPPORT_PAUSE
	| SUPPORT_STOP
	| SUPPORT_RETURN_HOME
	| SUPPORT_FAN_SPEED
	| SUPPORT_LOCATE
	| SUPPORT_SEND_COMMAND
	| SUPPORT_BATTERY
	| SUPPORT_START
)

STATE_CODE_TO_STATE = {
	0: STATE_IDLE,
	1: STATE_IDLE,
	2: STATE_PAUSED,
	3: STATE_CLEANING,
	4: STATE_RETURNING,
	5: STATE_DOCKED,
	6: STATE_CLEANING, # Vacuum & Mop
	7: STATE_CLEANING # Mop only
}

VACUUM_CARD_PROPS_REFERENCES = {
	'state_code': 'run_state',
	'mode': 'mode',
	'state': 'err_state',
	'battery': 'battary_life',
	'box_type': 'box_type',
	'mop_type': 'mop_type',
	'cleaned_area': 's_area',
	'cleaning_time': 's_time',
	'fanspeed': 'suction_grade',
	'water_grade': 'water_grade',
	'remember_map': 'remember_map',
	'has_map': 'has_map',
	'is_mop': 'is_mop',
	'has_newmap': 'has_newmap',
	'main_brush_life': 'main_brush_life',
	'main_brush_left': 'main_brush_hours',
	'side_brush_life': 'side_brush_life',
	'side_brush_left': 'side_brush_hours',
	'hypa_life': 'hypa_life',
	'filter_left': 'hypa_hours',
	'mop_life': 'mop_life',
	'sensor_dirty_left': 'mop_hours',
	'water_percent': 'water_percent',
	'hw_info': 'hw_info', 
	'sw_info': 'sw_info', 
	'start_time': 'start_time', 
	'order_time': 'order_time', 
	'v_state': 'v_state', 
	'zone_data': 'zone_data', 
	'repeat_state': 'repeat_state', 
	'light_state': 'light_state', 
	'is_charge': 'is_charge', 
	'is_work': 'is_work', 
	'cur_mapid': 'cur_mapid', 
	'mop_route': 'mop_route', 
	'map_num': 'map_num',
}

async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
	"""Set up the Xiaomi vacuum cleaner robot platform."""
	if DATA_KEY not in hass.data:
		hass.data[DATA_KEY] = {}

	host = config[CONF_HOST]
	token = config[CONF_TOKEN]
	name = config[CONF_NAME]

	# Create handler
	_LOGGER.info("Initializing with host %s (token %s...)", host, token[:5])
	vacuum = Vacuum(host, token)

	mirobo = MiroboVacuum2(name, vacuum)
	hass.data[DATA_KEY][host] = mirobo

	async_add_entities([mirobo], update_before_add=True)

async def async_service_handler(service):
	"""Map services to methods on MiroboVacuum."""
	method = SERVICE_TO_METHOD.get(service.service)
	params = {
		key: value for key,
		value in service.data.items() if key != ATTR_ENTITY_ID
	}
	entity_ids = service.data.get(ATTR_ENTITY_ID)

	if entity_ids:
		target_vacuums = [
			vac
			for vac in hass.data[DATA_KEY].values()
			if vac.entity_id in entity_ids
		]
	else:
		target_vacuums = hass.data[DATA_KEY].values()

	update_tasks = []
	for vacuum in target_vacuums:
		await getattr(vacuum, method["method"])(**params)

	for vacuum in target_vacuums:
		update_coro = vacuum.async_update_ha_state(True)
		update_tasks.append(update_coro)

	if update_tasks:
		await asyncio.wait(update_tasks)

	for vacuum_service in SERVICE_TO_METHOD:
		schema = SERVICE_TO_METHOD[vacuum_service].get(
			"schema", VACUUM_SERVICE_SCHEMA
		)
		hass.services.async_register(
			DOMAIN, vacuum_service, async_service_handler, schema=schema
		)

class MiroboVacuum2(StateVacuumEntity):
	"""Representation of a Xiaomi Vacuum cleaner robot."""

	def __init__(self, name, vacuum):
		"""Initialize the Xiaomi vacuum cleaner robot handler."""
		self._name = name
		self._vacuum = vacuum							   

		self.vacuum_state = None
		self._available = False

		self.last_clean_point = None
		#self.consumable_state = None
		#self.clean_history = None
		#self.dnd_state = None
		#self.last_clean = None
		#self._fan_speeds = None
		#self._fan_speeds_reverse = None

		#self._timers = None

	@property
	def name(self):
		"""Return the name of the device."""
		return self._name

	@property
	def state(self):
		"""Return the status of the vacuum cleaner."""
		if self.vacuum_state is not None:
			# The vacuum reverts back to an idle state after erroring out.
			# We want to keep returning an error until it has been cleared.

			try:
				return STATE_CODE_TO_STATE[int(self.vacuum_state['state_code'])]
			except KeyError:
				_LOGGER.error(
					"STATE not supported, state_code: %s",
					self.vacuum_state['state_code'],
				)
				return None

	@property
	def battery_level(self):
		"""Return the battery level of the vacuum cleaner."""
		if self.vacuum_state is not None:
			return self.vacuum_state['battery']

	@property
	def fan_speed(self):
		"""Return the fan speed of the vacuum cleaner."""
		if self.vacuum_state is not None:
			speed = self.vacuum_state['fanspeed']
			if speed in FAN_SPEEDS.values():
				return [
					key for key,
					value in FAN_SPEEDS.items() if value == speed][0]
			return speed

	@property
	def fan_speed_list(self):
		"""Get the list of available fan speed steps of the vacuum cleaner."""
		return list(sorted(FAN_SPEEDS.keys(), key=lambda s: FAN_SPEEDS[s]))

	@property
	def device_state_attributes(self):
		"""Return the specific state attributes of this vacuum cleaner."""
		attrs = {}
		if self.vacuum_state is not None:
			attrs.update(self.vacuum_state)
			try:
				attrs['status'] = STATE_CODE_TO_STATE[int(
					self.vacuum_state['state_code'])]
			except KeyError:
				return "Definition missing for state %s" % self.vacuum_state['state_code']
		return attrs

	@property
	def available(self) -> bool:
		"""Return True if entity is available."""
		return self._available

	@property
	def supported_features(self):
		"""Flag vacuum cleaner robot features that are supported."""
		return SUPPORT_XIAOMI

	async def _try_command(self, mask_error, func, *args, **kwargs):
		"""Call a vacuum command handling error messages."""
		try:
			await self.hass.async_add_executor_job(partial(func, *args, **kwargs))
			return True
		except DeviceException as exc:
			_LOGGER.error(mask_error, exc)
			return False

	async def async_start(self):
		"""Start or resume the cleaning task."""
		mode = self.vacuum_state['mode']
		is_mop = self.vacuum_state['is_mop']
		actionMode = 0

		if mode == 4 and self.last_clean_point is not None:
			method = 'set_pointclean'
			param = [1, self.last_clean_point[0], self.last_clean_point[1]]
		else:
			if mode == 2:
				actionMode = 2
			else:
				if is_mop == 2:
					actionMode = 3
				else:
					actionMode = is_mop
			if mode == 3:
				method = 'set_mode'
				param = [3, 1]
			else:
				method = 'set_mode_withroom'
				param = [actionMode, 1, 0]
		await self._try_command("Unable to start the vacuum: %s", self._vacuum.raw_command, method, param)

	async def async_pause(self):
		"""Pause the cleaning task."""
		mode = self.vacuum_state['mode']
		is_mop = self.vacuum_state['is_mop']
		actionMode = 0

		if mode == 4 and self.last_clean_point is not None:
			method = 'set_pointclean'
			param = [3, self.last_clean_point[0], self.last_clean_point[1]]
		else:
			if mode == 2:
				actionMode = 2
			else:
				if is_mop == 2:
					actionMode = 3
				else:
					actionMode = is_mop
			if mode == 3:
				method = 'set_mode'
				param = [3, 3]
			else:
				method = 'set_mode_withroom'
				param = [actionMode, 3, 0]
		await self._try_command("Unable to set pause: %s", self._vacuum.raw_command, method, param)

	async def async_stop(self, **kwargs):
		"""Stop the vacuum cleaner."""
		mode = self.vacuum_state['mode']
		if mode == 3:
			method = 'set_mode'
			param = [3, 0]
		elif mode == 4:
			method = 'set_pointclean'
			param = [0, 0, 0]
			self.last_clean_point = None
		else:
			method = 'set_mode'
			param = [0]
		await self._try_command("Unable to stop: %s", self._vacuum.raw_command, method, param)

	async def async_set_fan_speed(self, fan_speed, **kwargs):
		"""Set fan speed."""
		if fan_speed.capitalize() in FAN_SPEEDS:
			fan_speed = FAN_SPEEDS[fan_speed.capitalize()]
		else:
			try:
				fan_speed = int(fan_speed)
			except ValueError as exc:
				_LOGGER.error(
					"Fan speed step not recognized (%s). "
					"Valid speeds are: %s", exc, self.fan_speed_list,
				)
				return
		await self._try_command(
			"Unable to set fan speed: %s", self._vacuum.raw_command, 'set_suction', [fan_speed]
		)

	async def async_return_to_base(self, **kwargs):
		"""Set the vacuum cleaner to return to the dock."""
		await self._try_command(
			"Unable to return home: %s", self._vacuum.raw_command, 'set_charge', [1]
		)

	async def async_locate(self, **kwargs):
		"""Locate the vacuum cleaner."""
		await self._try_command(
			"Unable to locate the botvac: %s", self._vacuum.raw_command, 'set_resetpos', [1]
		)

	async def async_send_command(self, command, params=None, **kwargs):
		# Home Assistant templating always returns a string, even if array is outputted, fix this so we can use templating in scripts.
		if isinstance(params, list) and len(params) == 1 and isinstance(params[0], str):
			if params[0].find('[') > -1 and params[0].find(']') > -1:
				params = eval(params[0])
			elif params[0].isnumeric():
				params[0] = int(params[0])

		"""Send raw command."""
		await self._try_command(
			"Unable to send command to the vacuum: %s",
			self._vacuum.raw_command,
			command,
			params,
		)
		# self.update()

	def update(self):
		"""Fetch state from the device."""
		try:
			ALL_PROPS = list(VACUUM_CARD_PROPS_REFERENCES.values())
			state_values = self._vacuum.raw_command('get_prop', ALL_PROPS)
			state = dict(zip(ALL_PROPS, state_values))
			self.vacuum_state = dict()
			for prop in VACUUM_CARD_PROPS_REFERENCES.keys():
				self.vacuum_state[prop] = state[VACUUM_CARD_PROPS_REFERENCES[prop]]

			self._available = True

      	### Automatically set mop based on box_type
		##	is_mop = int(self.vacuum_state['is_mop'])
		##	box_type = int(self.vacuum_state['box_type'])
		##
		##	update_mop = None
		##	if box_type == 2 and is_mop != 2:
		##		update_mop = 2
		##	elif box_type == 3 and is_mop != 1:
		##		update_mop = 1
		##	elif box_type == 1 and is_mop != 0:
		##		update_mop = 0
		##
		##	if update_mop is not None:
		##		self._vacuum.raw_command('set_mop', [update_mop])
		##		self.update()
      	
		# Current state of the vacuum
        # 2: mop only, 1: dust&mop, 0: only vacuum
        current_mode = int(self.vacuum_state['is_mop'])
        # 3: 2 in 1, 2: water only, 1: dust only, 0: no box
        box_type = int(self.vacuum_state['box_type'])
		# True: has the mop attachment, False: no attachment
        has_mop = bool(self.vacuum_state['mop_type'])
		
		# Automatically set mop based on box_type
		new_mode = None

		if box_type == 3:
			# 2 in 1 box
			if has_mop:
				# Vacuum and mop if we have the attachment
				new_mode = 1
			else:
				# Just vacuum if we have no mop
				new_mode = 0
		elif box_type == 2:
			# We only have water, so let's mop.
			# (Vacuum will error out if we have no mop attachment)
			new_mode = 2
		elif box_type == 1:
			# We only have dust box, mopping not possible
			new_mode = 0

		if new_mode is not None and new_mode != current_mode:
			self._vacuum.raw_command('set_mop', [new_mode])
			self.update()

	except OSError as exc:
		_LOGGER.error("Got OSError while fetching the state: %s", exc)
	except DeviceException as exc:
		_LOGGER.warning("Got exception while fetching the state: %s", exc)

	async def async_clean_zone(self, zone, repeats=1):
		"""Clean selected area for the number of repeats indicated."""
		result = []
		i = 0
		for z in zone:
			x1, y2, x2, y1 = z
			res = '_'.join(str(x)
				for x in [i, 0, x1, y1, x1, y2, x2, y2, x2, y1])
			for _ in range(repeats):
				result.append(res)
				i += 1
		result = [i] + result

		await self._try_command("Unable to clean zone: %s", self._vacuum.raw_command, 'set_uploadmap', [1]) \
			and await self._try_command("Unable to clean zone: %s", self._vacuum.raw_command, 'set_zone', result) \
			and await self._try_command("Unable to clean zone: %s", self._vacuum.raw_command, 'set_mode', [3, 1])

	async def async_clean_point(self, point):
		"""Clean selected area"""
		x, y = point
		self.last_clean_point = point
		await self._try_command("Unable to clean point: %s", self._vacuum.raw_command, 'set_uploadmap', [0]) \
			and await self._try_command("Unable to clean point: %s", self._vacuum.raw_command, 'set_pointclean', [1, x, y])