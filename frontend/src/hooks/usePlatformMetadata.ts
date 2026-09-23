import { useQuery } from '@tanstack/react-query'
import { queryKeys } from '../api/queryKeys'
import { getPlatformMetadata, type PlatformMetadata } from '../services/platformService'
import type { ApiError } from '../types/api'

export const usePlatformMetadata = () => {
  return useQuery<PlatformMetadata, ApiError>({
    queryKey: queryKeys.platform.version,
    queryFn: getPlatformMetadata,
    staleTime: 60_000,
    retry: 1,
  })
}
