import { Loader2, Save, User } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api } from '../services/api'
import type { Profile } from '../types'

const EMPTY_PROFILE: Partial<Profile> = {
  display_name: '',
  age: undefined,
  sex: null,
  height_cm: undefined,
  weight_kg: undefined,
  activity_level: '',
  primary_goal: '',
  dietary_preferences: [],
  equipment: [],
  experience_level: '',
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

        <label className="profile__field">
          <span>Display name</span>
          <input
            type="text"
            value={profile.display_name ?? ''}
            onChange={(e) => handleChange('display_name', e.target.value)}
          />
        </label>

        <div className="profile__row">
          <label className="profile__field">
            <span>Age</span>
            <input
              type="number"
              min={10}
              max={120}
              value={profile.age ?? ''}
              onChange={(e) => handleChange('age', e.target.value ? Number(e.target.value) : undefined)}
            />
          </label>

          <label className="profile__field">
            <span>Sex</span>
            <select
              value={profile.sex ?? ''}
              onChange={(e) =>
                handleChange('sex', e.target.value === '' ? null : (e.target.value as 'male' | 'female'))
              }
            >
              <option value="">Not specified</option>
              <option value="male">Male</option>
              <option value="female">Female</option>
            </select>
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
            <option value="lightly_active">Lightly active</option>
            <option value="moderately_active">Moderately active</option>
            <option value="very_active">Very active</option>
            <option value="super_active">Super active</option>
          </select>
        </label>

        <label className="profile__field">
          <span>Primary goal</span>
          <input
            type="text"
            value={profile.primary_goal ?? ''}
            onChange={(e) => handleChange('primary_goal', e.target.value)}
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
          <span>Equipment</span>
          <input
            type="text"
            value={(profile.equipment ?? []).join(', ')}
            onChange={(e) =>
              handleChange(
                'equipment',
                e.target.value.split(',').map((s) => s.trim()).filter(Boolean),
              )
            }
            placeholder="e.g. dumbbells, barbell, resistance bands"
          />
        </label>

        <label className="profile__field">
          <span>Experience level</span>
          <select
            value={profile.experience_level ?? ''}
            onChange={(e) => handleChange('experience_level', e.target.value)}
          >
            <option value="">Select</option>
            <option value="beginner">Beginner</option>
            <option value="intermediate">Intermediate</option>
            <option value="advanced">Advanced</option>
          </select>
        </label>

        <button type="submit" className="profile__save" disabled={saving}>
          {saving ? <Loader2 className="page__spinner" size={18} /> : <Save size={18} />}
          Save profile
        </button>
      </form>
    </div>
  )
}
