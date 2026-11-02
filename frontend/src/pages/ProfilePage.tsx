import { Loader2, MapPin, Save, User, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useConfirmAction } from '../components/ui/ConfirmDialog'
import { api } from '../services/api'
import type { Profile, ProfilePreferences } from '../types'

const EMPTY_PROFILE: Partial<Profile> = {
  date_of_birth: undefined,
  age: undefined,
  height_cm: undefined,
  weight_kg: undefined,
  goal: '',
  activity_level: '',
  dietary_preferences: [],
  dietary_restrictions: [],
  preferences: {
    display_name: '',
    about_you: '',
    assistant_should_know: '',
    preferred_tone: '',
    units: 'metric',
    use_memory: true,
    reference_past_chats: true,
  },
}

export function ProfilePage() {
  const [profile, setProfile] = useState<Partial<Profile>>(EMPTY_PROFILE)
  const [original, setOriginal] = useState<Partial<Profile>>(EMPTY_PROFILE)
  const confirmAction = useConfirmAction()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [locating, setLocating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)
  useEffect(() => {
    api
      .getProfile()
      .then((p) => {
        const normalized = { ...EMPTY_PROFILE, ...p }
        setProfile(normalized)
        setOriginal(JSON.parse(JSON.stringify(normalized)))
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load profile'))
      .finally(() => setLoading(false))
  }, [])

  const dirty = JSON.stringify(profile) !== JSON.stringify(original)

  const handleChange = (field: keyof Profile, value: unknown) => {
    setProfile((prev) => ({ ...prev, [field]: value }))
    setSuccess(false)
  }

  const handlePreferenceChange = (field: keyof ProfilePreferences, value: unknown) => {
    setProfile((prev) => ({
      ...prev,
      preferences: { ...prev.preferences, [field]: value },
    }))
    setSuccess(false)
  }

  const discardChanges = () => {
    setProfile(JSON.parse(JSON.stringify(original)))
    setError(null)
    setSuccess(false)
  }

  const handleCancel = () => {
    if (!dirty) {
      discardChanges()
      return
    }
    confirmAction.request({
      title: 'Discard unsaved changes?',
      description: 'Your edits to this profile will be lost.',
      confirmLabel: 'Discard',
      onConfirm: discardChanges,
    })
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    setError(null)
    setSuccess(false)
    try {
      const updated = await api.updateProfile(profile)
      const normalized = { ...EMPTY_PROFILE, ...updated }
      setProfile(normalized)
      setOriginal(JSON.parse(JSON.stringify(normalized)))
      setSuccess(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save profile')
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
        <h1>Profile</h1>
        <p>Tell FitAI what matters to you. This shapes every answer.</p>
      </header>

      <form onSubmit={handleSubmit} className="profile__form">
        <div className="profile__avatar">
          <User size={40} />
        </div>

        {error && <div className="profile__alert profile__alert--error">{error}</div>}
        {success && <div className="profile__alert profile__alert--success">Profile saved.</div>}
        {dirty && <div className="profile__dirty">Unsaved changes</div>}

        <label className="profile__field">
          <span>Display name</span>
          <input
            type="text"
            value={profile.preferences?.display_name ?? ''}
            onChange={(e) => handlePreferenceChange('display_name', e.target.value)}
            placeholder="What should we call you?"
          />
        </label>

        <label className="profile__field">
          <span>About you</span>
          <textarea
            rows={3}
            value={profile.preferences?.about_you ?? ''}
            onChange={(e) => handlePreferenceChange('about_you', e.target.value)}
            placeholder="A few sentences about yourself"
          />
        </label>

        <label className="profile__field">
          <span>Things the assistant should know</span>
          <textarea
            rows={3}
            value={profile.preferences?.assistant_should_know ?? ''}
            onChange={(e) => handlePreferenceChange('assistant_should_know', e.target.value)}
            placeholder="Goals, routines, limitations, equipment, dietary preferences..."
          />
        </label>

        <label className="profile__field">
          <span>Preferred tone</span>
          <select
            value={profile.preferences?.preferred_tone ?? ''}
            onChange={(e) => handlePreferenceChange('preferred_tone', e.target.value)}
          >
            <option value="">Default</option>
            <option value="friendly">Friendly and casual</option>
            <option value="direct">Direct and concise</option>
            <option value="detailed">Detailed and explanatory</option>
            <option value="encouraging">Encouraging</option>
          </select>
        </label>

        <label className="profile__field">
          <span>Units</span>
          <select
            value={profile.preferences?.units ?? 'metric'}
            onChange={(e) => handlePreferenceChange('units', e.target.value)}
          >
            <option value="metric">Metric (kg, cm)</option>
            <option value="imperial">Imperial (lb, ft/in)</option>
          </select>
        </label>

        <div className="profile__toggle-group">
          <span className="profile__toggle-heading">Memory &amp; continuity</span>
          <label className="profile__toggle">
            <input
              type="checkbox"
              checked={profile.preferences?.use_memory ?? true}
              onChange={(e) => handlePreferenceChange('use_memory', e.target.checked)}
            />
            <span>Use my saved facts and fitness memory</span>
          </label>
          <label className="profile__toggle">
            <input
              type="checkbox"
              checked={profile.preferences?.reference_past_chats ?? true}
              onChange={(e) => handlePreferenceChange('reference_past_chats', e.target.checked)}
            />
            <span>Reference past chats</span>
          </label>
          <small className="profile__hint">
            These control what FitAI recalls from your history in every reply.
          </small>
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
            placeholder="e.g. Run a 5K, get stronger, sleep better"
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

        <div className="profile__field">
          <span>Location</span>
          <div className="profile__location">
            <input
              type="text"
              value={profile.location_label ?? ''}
              onChange={(e) => {
                handleChange('location_label', e.target.value || null)
                if (!e.target.value) {
                  handleChange('location_lat', null)
                  handleChange('location_lon', null)
                  handleChange('location_timezone', null)
                }
              }}
              placeholder="e.g. Mylapore, Chennai"
              aria-label="Location"
            />
            <button
              type="button"
              className="profile__location-btn"
              onClick={async () => {
                setLocating(true)
                setError(null)
                try {
                  const pos = await new Promise<GeolocationPosition>((resolve, reject) => {
                    navigator.geolocation.getCurrentPosition(resolve, reject, {
                      enableHighAccuracy: false,
                      timeout: 10000,
                    })
                  })
                  const roundedLat = Math.round(pos.coords.latitude * 1000) / 1000
                  const roundedLon = Math.round(pos.coords.longitude * 1000) / 1000
                  const result = await api.reverseGeocode(roundedLat, roundedLon)
                  handleChange('location_label', result.label)
                  handleChange('location_lat', result.lat)
                  handleChange('location_lon', result.lon)
                  handleChange('location_timezone', result.timezone ?? null)
                } catch (err) {
                  const msg = err instanceof GeolocationPositionError
                    ? 'Location permission denied or unavailable.'
                    : 'Could not look up location.'
                  setError(msg)
                } finally {
                  setLocating(false)
                }
              }}
              disabled={locating}
              aria-label="Use my current location"
              title="Use my current location"
            >
              {locating ? <Loader2 className="page__spinner" size={16} /> : <MapPin size={16} />}
            </button>
            {profile.location_label && (
              <button
                type="button"
                className="profile__location-btn"
                onClick={() => {
                  handleChange('location_label', null)
                  handleChange('location_lat', null)
                  handleChange('location_lon', null)
                  handleChange('location_timezone', null)
                }}
                aria-label="Clear location"
                title="Clear location"
              >
                <X size={16} />
              </button>
            )}
          </div>
          <small className="profile__hint">
            Used for local searches and weather. Coordinates are rounded to about 100m.
          </small>
        </div>

        <div className="profile__actions">
          <button type="submit" className="profile__save" disabled={saving || !dirty}>
            {saving ? <Loader2 className="page__spinner" size={18} /> : <Save size={18} />}
            Save
          </button>
          <button
            type="button"
            className="profile__cancel"
            onClick={handleCancel}
            disabled={!dirty}
          >
            <X size={18} />
            Cancel
          </button>
        </div>
      </form>
      {confirmAction.dialog}
    </div>
  )
}
