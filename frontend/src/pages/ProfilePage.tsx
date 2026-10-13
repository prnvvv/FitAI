import { Loader2, Save, User } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api } from '../services/api'
import type { Profile } from '../types'

const EMPTY_PROFILE: Partial<Profile> = {
  date_of_birth: undefined,
  age: undefined,
  height_cm: undefined,
  weight_kg: undefined,
  goal: '',
  activity_level: '',
  dietary_preferences: [],
  dietary_restrictions: [],
}

export function ProfilePage() {
  const [profile, setProfile] = useState<Partial<Profile>>(EMPTY_PROFILE)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    api
      .getProfile()
      .then((p) => setProfile(p))
      .catch(() => setProfile(EMPTY_PROFILE))
      .finally(() => setLoading(false))
  }, [])

  const handleChange = (field: keyof Profile, value: unknown) => {
    setProfile((prev) => ({ ...prev, [field]: value }))
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    try {
      const updated = await api.updateProfile(profile)
      setProfile(updated)
    } catch (err) {
      console.error(err)
      alert('Failed to save profile')
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="page page--loading">
        <Loader2 className="page__spinner" size={24} />
      </div>
    )
  }

  return (
    <div className="page page--profile">
      <header className="page__header">
        <h1>Fitness profile</h1>
        <p>Keep your stats up to date for better recommendations.</p>
      </header>

      <form onSubmit={handleSubmit} className="profile__form">
        <div className="profile__avatar">
          <User size={40} />
        </div>

        <div className="profile__row">
          <label className="profile__field">
            <span>Date of birth</span>
            <input
              type="date"
              value={profile.date_of_birth ?? ''}
              onChange={(e) => handleChange('date_of_birth', e.target.value || null)}
            />
          </label>

          <label className="profile__field">
            <span>Age</span>
            <input
              type="number"
              min={10}
              max={120}
              disabled
              value={profile.age ?? ''}
              placeholder="Derived from date of birth"
            />
          </label>
        </div>

        <div className="profile__row">
          <label className="profile__field">
            <span>Height (cm)</span>
            <input
              type="number"
              min={50}
              max={300}
              value={profile.height_cm ?? ''}
              onChange={(e) =>
                handleChange('height_cm', e.target.value ? Number(e.target.value) : undefined)
              }
            />
          </label>

          <label className="profile__field">
            <span>Weight (kg)</span>
            <input
              type="number"
              min={20}
              max={500}
              value={profile.weight_kg ?? ''}
              onChange={(e) =>
                handleChange('weight_kg', e.target.value ? Number(e.target.value) : undefined)
              }
            />
          </label>
        </div>

        <label className="profile__field">
          <span>Activity level</span>
          <select
            value={profile.activity_level ?? ''}
            onChange={(e) => handleChange('activity_level', e.target.value)}
          >
            <option value="">Select</option>
            <option value="sedentary">Sedentary</option>
            <option value="light">Lightly active</option>
            <option value="moderate">Moderately active</option>
            <option value="active">Active</option>
            <option value="very_active">Very active</option>
          </select>
        </label>

        <label className="profile__field">
          <span>Goal</span>
          <input
            type="text"
            value={profile.goal ?? ''}
            onChange={(e) => handleChange('goal', e.target.value)}
            placeholder="e.g. Build muscle, lose fat, run a 5K"
          />
        </label>

        <label className="profile__field">
          <span>Dietary preferences</span>
          <input
            type="text"
            value={(profile.dietary_preferences ?? []).join(', ')}
            onChange={(e) =>
              handleChange(
                'dietary_preferences',
                e.target.value.split(',').map((s) => s.trim()).filter(Boolean),
              )
            }
            placeholder="e.g. vegetarian, high-protein"
          />
        </label>

        <label className="profile__field">
          <span>Dietary restrictions</span>
          <input
            type="text"
            value={(profile.dietary_restrictions ?? []).join(', ')}
            onChange={(e) =>
              handleChange(
                'dietary_restrictions',
                e.target.value.split(',').map((s) => s.trim()).filter(Boolean),
              )
            }
            placeholder="e.g. lactose-free, gluten-free"
          />
        </label>

        <button type="submit" className="profile__save" disabled={saving}>
          {saving ? <Loader2 className="page__spinner" size={18} /> : <Save size={18} />}
          Save profile
        </button>
      </form>
    </div>
  )
}
