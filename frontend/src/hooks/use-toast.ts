export function useToast() {
  return {
    toast: (options: any) => {
      console.log('Toast:', options);
    },
  };
}
