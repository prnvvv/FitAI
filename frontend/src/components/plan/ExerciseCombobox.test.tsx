import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ExerciseCombobox } from './ExerciseCombobox'
import type { Exercise } from '../../types'

const library: Exercise[] = [
  {
    id: 'e1',
    slug: 'barbell_back_squat',
    name: 'Barbell Back Squat',
    primary_muscle_group: 'legs',
    equipment: 'barbell',
    movement_type: 'legs',
    unit_mode: 'reps_weight',
    is_custom: false,
  },
  {
    id: 'e2',
    slug: 'bulgarian_split_squat',
    name: 'Bulgarian Split Squat',
    primary_muscle_group: 'legs',
    equipment: 'dumbbell',
    movement_type: 'legs',
    unit_mode: 'reps_weight',
    is_custom: false,
  },
  {
    id: 'e3',
    slug: 'lat_pulldown',
    name: 'Lat Pulldown',
    primary_muscle_group: 'back',
    equipment: 'cable',
    movement_type: 'pull',
    unit_mode: 'reps_weight',
    is_custom: false,
  },
]

function mockApi() {
  const createExercise = vi.fn(async () => ({ ...library[0], id: 'e9', name: 'Cable Y raise', is_custom: true }))
  vi.doMock('../../services/api', async () => {
    const actual = await vi.importActual<typeof import('../../services/api')>('../../services/api')
    return { ...actual, api: { createExercise } }
  })
  return { createExercise }
}


/** The combobox is controlled, so tests drive it through a stateful wrapper. */
function Harness({
  library: items = library,
  recent = [] as Exercise[],
  onPick,
}: {
  library?: Exercise[]
  recent?: Exercise[]
  onPick?: (value: string, exercise: Exercise | null) => void
}) {
  const [value, setValue] = useState('')
  return (
    <ExerciseCombobox
      value={value}
      library={items}
      recent={recent}
      onChange={(next, exercise) => {
        setValue(next)
        onPick?.(next, exercise)
      }}
    />
  )
}

afterEach(() => {
  vi.resetModules()
  vi.restoreAllMocks()
})

describe('ExerciseCombobox', () => {
  it('searches by name as the user types', async () => {
    const user = userEvent.setup()
    render(<Harness />)

    await user.type(screen.getByLabelText('Exercise'), 'bulgar')
    expect(await screen.findByRole('option', { name: /Bulgarian Split Squat/ })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: /Lat Pulldown/ })).not.toBeInTheDocument()
  })

  it('searches by muscle group', async () => {
    const user = userEvent.setup()
    render(<ExerciseCombobox value="" onChange={vi.fn()} library={library} recent={[]} />)

    await user.type(screen.getByLabelText('Exercise'), 'back')
    expect(await screen.findByRole('option', { name: /Lat Pulldown/ })).toBeInTheDocument()
  })

  it('offers recently used exercises when empty', async () => {
    const user = userEvent.setup()
    render(<Harness recent={[library[2]]} />)

    await user.click(screen.getByLabelText('Exercise'))
    expect(await screen.findByText('Recent')).toBeInTheDocument()
    expect(screen.getByRole('option', { name: /Lat Pulldown/ })).toBeInTheDocument()
  })

  it('selects an option and reports the exercise', async () => {
    const onPick = vi.fn()
    const user = userEvent.setup()
    render(<Harness onPick={onPick} />)

    await user.type(screen.getByLabelText('Exercise'), 'lat')
    await user.click(await screen.findByRole('option', { name: /Lat Pulldown/ }))

    expect(onPick).toHaveBeenCalledWith('Lat Pulldown', library[2])
  })

  it('supports keyboard selection', async () => {
    const onPick = vi.fn()
    const user = userEvent.setup()
    render(<Harness onPick={onPick} />)

    const input = screen.getByLabelText('Exercise')
    await user.click(input)
    await user.keyboard('{ArrowDown}{Enter}')

    expect(onPick).toHaveBeenCalledWith('Barbell Back Squat', library[0])
  })

  it('allows free text', async () => {
    const onPick = vi.fn()
    const user = userEvent.setup()
    render(<Harness onPick={onPick} />)

    await user.type(screen.getByLabelText('Exercise'), 'My own move')
    expect(onPick).toHaveBeenLastCalledWith('My own move', null)
  })

  it('creates a custom exercise when nothing matches', async () => {
    const { createExercise } = mockApi()
    const onPick = vi.fn()
    const user = userEvent.setup()
    vi.resetModules()
    const module = await import('./ExerciseCombobox')
    function CreateHarness() {
      const [value, setValue] = useState('')
      return (
        <module.ExerciseCombobox
          value={value}
          library={library}
          recent={[]}
          onChange={(next, exercise) => {
            setValue(next)
            onPick(next, exercise)
          }}
        />
      )
    }
    render(<CreateHarness />)

    await user.type(screen.getByLabelText('Exercise'), 'Cable Y raise')
    await user.click(await screen.findByRole('button', { name: /Create/ }))

    await waitFor(() => expect(createExercise).toHaveBeenCalledWith({ name: 'Cable Y raise' }))
    await waitFor(() =>
      expect(onPick).toHaveBeenLastCalledWith('Cable Y raise', expect.objectContaining({ is_custom: true })),
    )
  })
})
