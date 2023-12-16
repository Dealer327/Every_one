from aiogram.types import Message, CallbackQuery
from dateutil.relativedelta import relativedelta

from aiogram.filters import CommandStart, StateFilter
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup, default_state

from ..services.file_handling import create_day, create_button_main_menu
from ....models import *
from ..keyboards.main_menu import create_inline_kb, create_button_back_and_mani_menu
from ..keyboards.calendar_kb import create_calendar, create_kb_yes_or_no, create_kb_finish_add_event, \
    create_list_events, CallbackFactoryForEvent
from ..lexicon.lexicon_ru import Lexicon_ru, Lexicon_month, Lexicon_form_new_event
from ..date_base import datebase

# Инициализируем роутер уровня модуля
router: Router = Router()


# Форма состояний для заполнения информации про эвента
class FormEvent(StatesGroup):
    start_time = State()
    name_even = State()
    info_event = State()
    # url_event = State()


class FormOpenEvents(StatesGroup):
    open_day = State()


@router.message(CommandStart())
async def process_start_command(message: Message):
    await Profile.objects.aget_or_create(
        external_id=message.from_user.id,
        defaults={'name': message.from_user.username})
    all_not_read_events = await datebase.show_count_not_read_event_in_menu(message.from_user.id)
    keyboard_menu = create_inline_kb(1, all_not_read_events, 'calendar', 'new_event')
    await message.answer(
        text=Lexicon_ru['/start'],
        reply_markup=keyboard_menu
    )


# Хендлер для срабатывания на нажатия кнопки добавить свое событие
@router.callback_query(F.data == 'new_event', StateFilter(default_state))
async def create_new_event(callback: CallbackQuery, state: FSMContext):
    await state.set_state(FormEvent.start_time)
    await callback.message.edit_text(
        text=f'{Lexicon_form_new_event["Date_event"]}',
        reply_markup=create_button_main_menu())
    await callback.answer()


# Хендлер для срабатывания отправки даты и времени начала эвента
@router.message(StateFilter(FormEvent.start_time))
async def process_input_date(message: Message, state: FSMContext):
    await state.update_data(start_time=message.text)
    try:
        datetime.strptime(message.text, '%Y-%m-%d %H:%M').date()
        await state.set_state(FormEvent.name_even)
        await message.answer(
            text=f"{Lexicon_form_new_event['Conf_date']} {message.text}",
            reply_markup=create_kb_yes_or_no(2, 'Yes_date', 'No_date')
        )
        await message.delete()
    except ValueError:
        await message.answer(text=f'{Lexicon_form_new_event["Error_date"]}',
                             reply_markup=create_button_main_menu())


# хендлер для заполнения названия эвента
@router.message(StateFilter(FormEvent.name_even))
async def process_input_name_event(message: Message, state: FSMContext):
    await state.update_data(name_event=message.text)
    await state.set_state(FormEvent.info_event)
    await message.answer(text=f"{Lexicon_form_new_event['Conf_name']} {message.text}",
                         reply_markup=create_kb_yes_or_no(2, 'Yes', 'No'))
    await message.delete()


# хендлер условного подтверждения заполненной формы даты и названия мероприятия
@router.callback_query(lambda f: f.data == 'Yes' or f.data == 'Yes_date')
async def process_next_form(callback: CallbackQuery, state: FSMContext):
    if callback.data == 'Yes':
        current_state = await state.get_state()
        if current_state is None:
            return
        await callback.message.edit_text(text=f'{Lexicon_form_new_event["Info_event"]}',
                                         reply_markup=create_button_main_menu()
                                         )
        await callback.answer()
    else:
        await callback.message.edit_text(text=f'{Lexicon_form_new_event["Hi_event"]}',
                                         reply_markup=create_button_main_menu())
        await callback.answer()


# хендлер для вывода полной информации про эвента и заполнения информации
@router.message(StateFilter(FormEvent.info_event))
async def process_input_info_event(message: Message, state: FSMContext):
    await state.update_data(info_event=message.text)
    data = await state.get_data()
    await message.answer(text=f'{Lexicon_form_new_event["Conf_info"]} '
                              f'{data["name_event"]} '
                              f'{data["info_event"]} '
                              f' {data["start_time"]}',
                         reply_markup=create_kb_finish_add_event(2, 'Reg', 'Cen')
                         )
    await message.delete()


# хендлер регистрации эвента и добавления его в бд
@router.callback_query(F.data == 'Reg')
async def save_info_in_db(callback: CallbackQuery, state: FSMContext, bot):
    p = await Profile.objects.aget(name=callback.from_user.username)
    keyboard_menu = create_inline_kb(1, None, 'calendar', 'new_event')
    try:
        data = await state.get_data()
        event = Event(name_event=data['name_event'],
                      info_event=data['info_event'],
                      user_create=p,
                      start_time=data['start_time'])

        admins = await datebase.all_admins()
        for a in admins:
            await bot.send_message(chat_id=a, text=f'{event.name_event}\n'
                                                   f'{event.info_event}\n'
                                                   f'{event.start_time}\n'
                                                   f'{event.user_create}')
        await callback.message.edit_text(
            text=Lexicon_ru['/start'],
            reply_markup=keyboard_menu
        )
        await event.asave()
        await state.clear()
        # ДОДЕЛАТЬ: возможность добавлять одно событие

        await callback.answer()
    except ValueError:
        await callback.message.edit_text(
            text=Lexicon_ru['/start'],
            reply_markup=keyboard_menu
        )


# вывод календаря
@router.callback_query(lambda f: f.data == 'calendar' or f.data == 'back_in_calendar')
async def process_open_calendar(callback: CallbackQuery):
    u = callback.from_user.id
    p = await datebase.up_date_time_for_user(callback)
    name_month = callback.message.date.month
    list_days = create_day(callback.message.date.year, callback.message.date.month)
    events = await datebase.show_events_now_month(u,
                                                  p.time_update.year,
                                                  p.time_update.month,
                                                  p.time_update.day
                                                  )
    await callback.message.edit_text(
        text=f'<b>Календарь событий {p.choice_month.year}</b> ',
        reply_markup=create_calendar(3,
                                     events,
                                     list_days,
                                     'backward_c',
                                     f'{Lexicon_month[name_month]}',
                                     'forward_c',
                                     last_btn='Главное меню'))
    await callback.answer()


# хендлер отслеживающий нажатие на день в календаре
@router.callback_query(lambda c: c.data and c.data.isdigit() and int(c.data) <= 31 or c.data == 'back_in_events')
async def process_pres_day(callback: CallbackQuery, state: FSMContext):
    if callback.data != 'back_in_events':
        await state.update_data(open_day=callback.data)
        events = await datebase.show_events_press_day(int(callback.data), callback.from_user.id)
        await callback.message.edit_text(text='Список',
                                         reply_markup=create_list_events(
                                             1,
                                             events,
                                             'mani_menu',
                                             'back_in_calendar'
                                         ))
        await callback.answer()
    else:
        s = await state.get_data()
        events = await datebase.show_events_press_day(int(s['open_day']), callback.from_user.id)
        await callback.message.edit_text(text='Список',
                                         reply_markup=create_list_events(
                                             1,
                                             events,
                                             'mani_menu',
                                             'back_in_calendar'
                                         ))
        await callback.answer()


# хендлер для отслеживания нажатого эвента в списке
@router.callback_query(CallbackFactoryForEvent.filter())
async def show_info_about_event(callback: CallbackQuery, callback_data: CallbackFactoryForEvent):
    is_user = await Profile.objects.aget(external_id=callback.from_user.id)
    event_info = await datebase.show_info_about_event(callback_data.id_event)
    await EventIsRead.objects.aget_or_create(profile=is_user, event=event_info)
    await callback.message.edit_text(text=f'{event_info.name_event}\n'
                                          f'{event_info.info_event}\n'
                                          f'Начало: {event_info.start_time.strftime("%Y-%m-%d в %H:%M")}',
                                     reply_markup=create_button_back_and_mani_menu(1,
                                                                                   'back_in_events',
                                                                                   'mani_menu'
                                                                                   ))


# хендлер для перелистывания месяцев в календаре
@router.callback_query(lambda f: f.data == 'forward_c' or f.data == 'backward_c')
async def process_next_month(callback: CallbackQuery):
    m = await Profile.objects.aget(external_id=callback.from_user.id)
    time_for_now_month = datetime.now()
    if callback.data == 'forward_c':
        m.choice_month = m.choice_month + relativedelta(months=+1, day=1)
        await m.asave(update_fields=['choice_month'])
    else:
        m.choice_month = m.choice_month + relativedelta(months=-1, day=1)
        await m.asave(update_fields=['choice_month'])
    list_days = create_day(m.choice_month.year, m.choice_month.month)
    if m.choice_month.month != time_for_now_month.month:
        events = await datebase.show_events_now_month(m, m.choice_month.year, m.choice_month.month, m.choice_month.day)
    else:
        events = await datebase.show_events_now_month(m, m.choice_month.year, m.choice_month.month,
                                                      time_for_now_month.day)
    await callback.message.edit_text(
        text=f'<b>Календарь событий {m.choice_month.year}</b> ',
        reply_markup=create_calendar(3,
                                     events,
                                     list_days,
                                     'backward_c',
                                     f'{Lexicon_month[m.choice_month.month]}',
                                     'forward_c',
                                     last_btn='Главное меню')
    )
    await callback.answer()


# хендлер отслеживающий на нажатие кнопок ведущих в главное меню
@router.callback_query(lambda f:
                       f.data == 'last_btn' or
                       f.data == 'No' or
                       f.data == 'Cen' or
                       f.data == 'No_date' or
                       f.data == 'mani_menu'
                       )
async def process_open_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    all_not_read_events = await datebase.show_count_not_read_event_in_menu(callback.from_user.id)
    keyboard_menu = create_inline_kb(1, all_not_read_events, 'calendar', 'new_event')
    await callback.message.edit_text(
        text=Lexicon_ru['/start'],
        reply_markup=keyboard_menu)
    await callback.answer()
